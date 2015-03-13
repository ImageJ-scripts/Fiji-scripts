import sys
import os
import glob
import time
import math
import shutil
import xml.etree.ElementTree as etree

import ij
from ij import IJ
from ij import ImageStack, ImagePlus
from ij.io import OpenDialog
from ij.process import ShortProcessor
from fiji.util.gui import GenericDialogPlus

from loci.plugins import BF
from loci.plugins.in import ImporterOptions
from loci.formats import ImageReader,ImageWriter
from loci.formats import MetadataTools
from loci.common import DataTools
from loci.common import RandomAccessInputStream
from loci.common import RandomAccessOutputStream
from loci.formats.tiff import TiffParser
from loci.formats.tiff import TiffSaver

from ome.xml.meta import OMEXMLMetadata
from ome.xml.model.primitives import PositiveInteger,PositiveFloat
from ome.xml.model.primitives import NonNegativeInteger as NNI
from ome.xml.model.enums import DimensionOrder, PixelType

from java.lang import StringBuffer

def delete_slices(slices_dir):
	try:
		for name in glob.glob("%simg*" % (slices_dir)):
			os.remove(name)
	except:
		pass 

def restore_metadata(input_dir,original_metadata,prefix):
	# restore original metadata and filename to tiles
	rewritten_data = glob.glob("%s*.tiff"%input_dir)
	for f,filename in enumerate(rewritten_data):
		new_filename = prefix+os.path.basename(filename)
		IJ.log("Rewriting original meta data in image %s"%os.path.basename(new_filename))
		replace_meta(original_metadata[f],filename)
		os.rename(filename,new_filename)

def link_slices(output_path,channel,sizeZ,theC,physX,physY,physZ):

	IJ.log("Linking z slices")

	# number of slices will determine filename format
	digits = "00"
	if sizeZ < 100:
		digits = "0"
	if sizeZ < 10:
		digits = ""

	# get the base metadata from the first fused image
	z0meta = MetadataTools.createOMEXMLMetadata()
	fused = glob.glob(output_path + "fused*")
	first_fused = fused[0]
	reader = get_reader(first_fused,z0meta)
	z0meta.setPixelsSizeZ(PositiveInteger(sizeZ),0)
	reader.close()

	for z in range(sizeZ):
		fpath = fused[z]
		IJ.log("writing metadata to slice %s"%os.path.basename(fpath))
		m = MetadataTools.createOMEXMLMetadata()
		r = get_reader(fpath,m)

		# set the TiffData elements on the first plane
		# setTiffData(IFD, image index, TiffData index)
		z0meta.setTiffDataIFD(NNI(0),0,z)
		# setTiffDataPlaneCount(planecount, image index, TiffData index)
		z0meta.setTiffDataPlaneCount(NNI(1),0,z)
		# setTiffDataFirstC(firstC, image index, TiffData index)
		z0meta.setTiffDataFirstC(NNI(0),0,z)
		# setTiffDataFirstC(firstT, image index, TiffData index)
		z0meta.setTiffDataFirstT(NNI(0),0,z)
		# setTiffDataFirstC(firstZ, image index, TiffData index)
		z0meta.setTiffDataFirstZ(NNI(0),z,z)
		# setUUIDFileName(filename, image index, TiffData index)
		z0meta.setUUIDFileName(m.getUUIDFileName(0,0),0,0)
		# setUUIDValue(value, image index, TiffData index)
		z0meta.setUUIDValue(m.getUUIDValue(0,0),0,0)

		# set the physical pixel sizes on each plane
		m.setPixelsPhysicalSizeX(physX,0)
		m.setPixelsPhysicalSizeY(physY,0)
		m.setPixelsPhysicalSizeZ(physZ,0)

		# set the channel attributes on each plane
		m.setChannelID("Channel:0:" + str(0), 0, 0)
		spp = channel['spp']
		m.setChannelSamplesPerPixel(spp, 0, 0)
		name = channel['name']
		color = channel['color']
		m.setChannelName(name,0,0)
		m.setChannelColor(color,0,0)
		r.close()

		# replace the metadata in the slice
		if z > 0:
			replace_meta(m,fpath)

	replace_meta(z0meta,first_fused)

	
def write_fused(output_path,channel,sizeZ,theC,physX,physY,physZ):

	IJ.log("Writing fused data")

	# number of slices will determine filename format
	digits = "00"
	if sizeZ < 100:
		digits = "0"
	if sizeZ < 10:
		digits = ""

	# get the base metadata from the first fused image
	meta = MetadataTools.createOMEXMLMetadata()
	reader = get_reader(output_path+"img_t1_z%s1_c1"%digits,meta)
	reader.close()
	get_tiffdata(meta)
	# reset some metadata
	meta.setPixelsPhysicalSizeX(physX,0)
	meta.setPixelsPhysicalSizeY(physY,0)
	meta.setPixelsPhysicalSizeZ(physZ,0)
	meta.setPixelsSizeZ(PositiveInteger(sizeZ),0)
	meta.setChannelID("Channel:0:" + str(0), 0, 0)
	spp = channel['spp']
	meta.setChannelSamplesPerPixel(spp, 0, 0)
	name = channel['name']
	color = channel['color']
	meta.setChannelName(name,0,0)
	meta.setChannelColor(color,0,0)
		
	# determine the number of subsets that need to be written
	slices_per_subset = 200
	num_output_files = divmod(sizeZ,slices_per_subset)
	fpaths = []
	if num_output_files[0] == 0:
		nslices = [sizeZ]
		num_output_files = 1
		fpaths.append("%sfused_C%s.ome.tif"%(output_path,str(theC-1)))
	else:
		nslices = []
		for n in range(num_output_files[0]):
			nslices.append(slices_per_subset)

		if num_output_files[1] > 0:
			nslices.append(num_output_files[1])		
		
		for s in range(len(nslices)):
			fpaths.append("%sfused_C%s_subset%s.ome.tif"%(output_path,str(theC-1),str(s)))

	# setup a writer
	writer = ImageWriter()
	writer.setCompression('LZW')
	writer.setMetadataRetrieve(meta)
	writer.setId(fpaths[0])

	# write the slices, changing the output file when necessary
	theZ = 0
	for f in range(len(fpaths)):
		meta.setImageName(os.path.basename(fpaths[f]),0)
		writer.changeOutputFile(fpaths[f])
		for s in range(nslices[f]):
			fpath = output_path+"img_t1_z%s%s_c1"%(digits,str(theZ+1))
			if (len(digits) == 1) and (theZ+1 > 9):
				fpath = output_path+"img_t1_z%s_c1"%(str(theZ+1))
			if (len(digits) == 2) and (theZ+1 > 9):
				fpath = output_path+"img_t1_z0%s_c1"%(str(theZ+1))
			if (len(digits) == 2) and (theZ+1 > 99):
				fpath = output_path+"img_t1_z%s_c1"%(str(theZ+1))
			IJ.log("writing slice %s"%os.path.basename(fpath))
			m = MetadataTools.createOMEXMLMetadata()
			print "tiffData",m.getTiffData()
			r = get_reader(fpath,m)
			m.setPixelsPhysicalSizeX(physX,0)
			m.setPixelsPhysicalSizeY(physY,0)
			m.setPixelsPhysicalSizeZ(physZ,0)
			m.setChannelID("Channel:0:" + str(0), 0, 0)
			spp = channel['spp']
			m.setChannelSamplesPerPixel(spp, 0, 0)
			name = channel['name']
			color = channel['color']
			m.setChannelName(name,0,0)
			m.setChannelColor(color,0,0)
			writer.saveBytes(theZ,r.openBytes(0))
			r.close()
			theZ += 1
	writer.close()

def run_stitching(tiles_dir,tile_name,gridX, gridY):
	IJ.run("Grid/Collection stitching", "type=[Grid: snake by rows] order=[Right & Down                ] "\
			"grid_size_x=%s grid_size_y=%s tile_overlap=20 first_file_index_i=0 "\
			"directory=[%s] file_names=[%s] "\
			"output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] "\
			"regression_threshold=0.30 max/avg_displacement_threshold=2.50 "\
			"absolute_displacement_threshold=3.50 compute_overlap "\
			"computation_parameters=[Save memory (but be slower)] "\
			"image_output=[Write to disk] output_directory=[%s]"%(gridX,gridY,tiles_dir,tile_name,tiles_dir))

def replace_meta(meta,filename):
	newComment = meta.dumpXML()
	instream = RandomAccessInputStream(filename)
	outstream = RandomAccessOutputStream(filename)
	saver = TiffSaver(outstream, filename)
	saver.overwriteComment(instream, newComment)
	instream.close()
	outstream.close()

def set_metadata(inputMeta,outputMeta,chan):

	outputMeta.setImageID("Image:0", 0)
	outputMeta.setPixelsID("Pixels:0", 0)
	outputMeta.setPixelsBinDataBigEndian(False, 0, 0)
	outputMeta.setPixelsDimensionOrder(DimensionOrder.XYCZT, 0)
	outputMeta.setPixelsType(inputMeta.getPixelsType(0),0)
	outputMeta.setPixelsPhysicalSizeX(inputMeta.getPixelsPhysicalSizeX(0),0)
	outputMeta.setPixelsPhysicalSizeY(inputMeta.getPixelsPhysicalSizeY(0),0)
	outputMeta.setPixelsPhysicalSizeZ(inputMeta.getPixelsPhysicalSizeZ(0),0)
	outputMeta.setPixelsSizeX(inputMeta.getPixelsSizeX(0),0)
	outputMeta.setPixelsSizeY(inputMeta.getPixelsSizeY(0),0)
	outputMeta.setPixelsSizeZ(inputMeta.getPixelsSizeZ(0),0)
	outputMeta.setPixelsSizeC(PositiveInteger(1),0)
	outputMeta.setPixelsSizeT(PositiveInteger(1),0)

	outputMeta.setChannelID("Channel:0:" + str(0), 0, 0)
	spp = chan['spp']
	outputMeta.setChannelSamplesPerPixel(spp, 0, 0)
	name = chan['name']
	color = chan['color']
	outputMeta.setChannelName(name,0,0)
	outputMeta.setChannelColor(color,0,0)
	
	return outputMeta

def pixel_info(meta):
	physX = meta.getPixelsPhysicalSizeX(0)
	physY = meta.getPixelsPhysicalSizeY(0)
	physZ = meta.getPixelsPhysicalSizeZ(0)
	return physX,physY,physZ

def tile_info(meta):
	tiles = meta.getPixelsSizeT(0).getValue()
	slices = meta.getPixelsSizeZ(0).getValue()
	return tiles,slices

def channel_info(meta):
	sizeC = meta.getPixelsSizeC(0).getValue()
	channels = []
	for c in range(sizeC):
		chan_d = {}
		chan_d['spp'] = meta.getChannelSamplesPerPixel(0,c)
		chan_d['name'] = meta.getChannelName(0,c)
		chan_d['color'] = meta.getChannelColor(0,c)
		chan_d['ID'] = c
		channels.append(chan_d)
	return channels
		
def get_reader(file, complete_meta):
	reader = ImageReader()
	reader.setMetadataStore(complete_meta)
	reader.setId(file)
	return reader

def run_script(params):

	input_dir = params['directory']
	gridX = params['gridX']
	gridY = params['gridY']
	select_channel = params['select_channel']
	channel = params['channel']

	input_data = glob.glob("%s*.tiff"%input_dir)
	first = [s for s in input_data if "T0_C0" in s][0]
	start = first.index("Z")+1
	sub = first[start:]
	stop = sub.index("_")
	digits = sub[:stop-1]
	sep = os.path.sep
			
	original_metadata = []
	for filename in input_data:
		meta = MetadataTools.createOMEXMLMetadata()
		reader = get_reader(filename,meta)
		original_metadata.append(meta)
		reader.close()

	complete_meta = original_metadata[0]
	channels_meta = channel_info(complete_meta)
	if len(input_data) != (gridX * gridY * len(channels_meta)):
		IJ.log("Stopped stitching - gridX or gridY not set correctly")
		return
	
	channels = channels_meta
	if select_channel:
		channels = [channels_meta[channel]] # a list of len 1 with a dictionary of channel metadata
		
	num_tiles,num_slices = tile_info(complete_meta)
	if params['separate_z']:
		sizeZ = num_slices
	else:
		sizeZ = 1
		
	for z in range(sizeZ):
		for t in range(num_tiles):
			for c,chan in enumerate(channels):
				frag = "Z%s%s_T%s_C%s"%(digits,z,t,chan['ID'])
				input_path = [s for s in input_data if frag in s][0]
				IJ.log("Transforming metadata in image %s"%os.path.basename(input_path))
				tile_meta = MetadataTools.createOMEXMLMetadata()
				tile_meta = set_metadata(complete_meta,tile_meta,chan)
				replace_meta(tile_meta,input_path)

	idx = input_data[0].index("Z%s0_T0_C0.tiff"%digits)
	prefix = input_data[0][:idx]
	trunc_filenames = []
	for filename in input_data:
		new_filename = input_dir+filename[idx:]
		os.rename(filename,new_filename)
		trunc_filenames.append(new_filename)

	while not os.path.exists(trunc_filenames[-1]):
	   time.sleep(1)
		
	physX,physY,physZ = pixel_info(complete_meta)	
	for c,chan in enumerate(channels):
		tile_names = "Z%s0_T{i}_C%s.tiff"%(digits,chan['ID'])
		run_stitching(input_dir,tile_names,gridX,gridY)
		restore_metadata(input_dir,original_metadata,prefix)
		write_fused(input_dir,chan,num_slices,c+1,\
					physX,physY,physZ) # channel index starts at 1

	delete_slices(input_dir)
		
def make_dialog():

	parameters = {}

	gd = GenericDialogPlus("Grid Stitch SDC Data")
	gd.addMessage(  "Warning!\n"\
					"In order to display a fused image upon completion of stitching\n"\
					"please disable Fiji's ImageJ2 options. When enabled an ImageJ\n"\
					"exception will be displayed upon completion. This exception can\n"
					"be safely ignored.")
	gd.addMessage(  "Information\n"\
					"This plugin is a wrapper around the Fiji 'Grid Stitching' plugin.\n"\
					"It allows tiles generated in SlideBook to be directly stitched by\n"\
					"by first writing out the individual tiles, executing the 'Grid Stitching'\n"\
					"plugin and writing the fused image to disk.")
	gd.addMessage("")										
	gd.addNumericField("grid_size_x", 3, 0)
	gd.addNumericField("grid_size_y", 3, 0)
	gd.addCheckbox("Select channel",False)
	gd.addNumericField("", 0, 0)		
	gd.addCheckbox("Are the Z slices separate files?",False)
	gd.addDirectoryField("directory", "", 50)
	
	gd.showDialog()
	if (gd.wasCanceled()): return
		
	parameters['gridX'] = int(math.ceil(gd.getNextNumber()))
	parameters['gridY'] = int(math.ceil(gd.getNextNumber()))
	parameters['select_channel'] = gd.getNextBoolean()
	parameters['channel'] = None
	if parameters['select_channel']:
		parameters['channel'] = int(gd.getNextNumber())
	
	directory = str(gd.getNextString())	
	if directory is None:
	# User canceled the dialog
		return None
	else:
		directory = os.path.abspath(directory)
		parameters['directory'] = directory + os.path.sep

	return parameters

if __name__=='__main__':

	params = make_dialog()
	run_script(params)
