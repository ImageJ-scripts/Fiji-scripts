import sys
import os
import glob
import time
import math
import shutil
import xml.etree.ElementTree as ET

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
from ome.xml.model.enums import DimensionOrder, PixelType

from java.lang import StringBuffer

def delete_slices(slices_dir):
	try:
		for name in glob.glob("%simg*" % (slices_dir)):
			os.remove(name)
	except:
		pass 

def write_fused(output_path,channel,sizeZ,theC):

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
	
	# reset some metadata
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
			r = get_reader(fpath,m)
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
		channels.append(chan_d)
	return channels
		
def get_reader(file, complete_meta):
	reader = ImageReader()
	reader.setMetadataStore(complete_meta)
	reader.setId(file)
	return reader

def run_script(input_dir,gridX,gridY,select_channel,channel):

	input_data = glob.glob("%s*.tiff"%input_dir)
	first = [s for s in input_data if "T0_C0" in s][0]
	start = first.index("Z")+1
	sub = first[start:]
	stop = sub.index("_")
	digits = sub[:stop]
	sep = os.path.sep
	print digits
	original_metadata = []
	for filename in input_data:
		IJ.log("Transforming metadata in image %s"%os.path.basename(filename))
		meta = MetadataTools.createOMEXMLMetadata()
		reader = get_reader(filename,meta)
		original_metadata.append(meta)
		reader.close()

	complete_meta = original_metadata[0]
	channels = channel_info(complete_meta)
	num_tiles,num_slices = tile_info(complete_meta)
	for t in range(num_tiles):
		for c,chan in enumerate(channels):
			frag = "Z%s_T%s_C%s"%(digits,t,c)
			input_path = [s for s in input_data if frag in s][0]
			tile_meta = MetadataTools.createOMEXMLMetadata()
			tile_meta = set_metadata(complete_meta,tile_meta,chan)
			replace_meta(tile_meta,input_path)

	idx = input_data[0].index("Z%s_T0_C0.tiff"%digits)
	prefix = input_data[0][:idx]
	for filename in input_data:
		os.rename(filename,input_dir+filename[idx:])
		
	if select_channel:
		tile_names = "Z%s_T{i}_C%s.tiff"%(digits,channel)
		run_stitching(input_dir,tile_names,gridX,gridY)
		write_fused(input_dir,channels[channel],num_slices,channel+1) # channel index starts at 1
	else:
		for theC in range(len(channels)):
			tile_names = "Z%s_T{i}_C%s.tiff"%(digits,theC)
			run_stitching(input_dir,tile_names,gridX,gridY)
			write_fused(input_dir,channels[theC],num_slices,theC+1) # channel index starts at 1

	# restore original metadata and filename to tiles
	rewritten_data = glob.glob("%s*.tiff"%input_dir)
	for f,filename in enumerate(rewritten_data):
		new_filename = prefix+os.path.basename(filename)
		IJ.log("Rewriting original meta data in image %s"%os.path.basename(new_filename))
		replace_meta(original_metadata[f],filename)
		os.rename(filename,new_filename)

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
	input_dir = params['directory']
	gridX = params['gridX']
	gridY = params['gridY']
	select_channel = params['select_channel']
	channel = params['channel']

	run_script(input_dir,gridX,gridY,select_channel,channel)
