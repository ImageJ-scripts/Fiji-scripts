import sys
import os
import glob
import time
import math
import shutil

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

from ome.xml.meta import OMEXMLMetadata
from ome.xml.model.primitives import PositiveInteger,PositiveFloat
from ome.xml.model.enums import DimensionOrder, PixelType

from java.lang import StringBuffer

def delete_tiles(tiles_dir):
	try:
		for name in glob.glob("%s*" % (tiles_dir)):
			os.remove(name)
		
		shutil.rmtree(tiles_dir)
	except:
		pass 

def write_fused(output_path,meta):
	imp = ij.WindowManager.getCurrentImage()
	planes = imp.getStack()
	
	meta.setPixelsSizeX(PositiveInteger(imp.getWidth()),0)
	meta.setPixelsSizeY(PositiveInteger(imp.getHeight()),0)
	writer = ImageWriter()
	writer.setCompression('LZW')
	writer.setMetadataRetrieve(meta)
	file_path = "%sfused.ome.tif"%output_path
	if os.path.exists(file_path):
		os.remove(file_path)
	writer.setId(file_path)
	print writer.getFormat()
	littleEndian = not writer.getMetadataRetrieve().getPixelsBinDataBigEndian(0, 0)
	
	for p in range(planes.getSize()):
		proc = planes.getProcessor(p+1)
		writer.saveBytes(p,DataTools.shortsToBytes(proc.getPixels(), littleEndian))
	writer.close()
	
def run_stitching(tiles_dir,tile_name,gridX, gridY):
	IJ.run("Grid/Collection stitching", "type=[Grid: snake by rows] order=[Right & Down                ] "\
			"grid_size_x=%s grid_size_y=%s tile_overlap=20 first_file_index_i=0 "\
			"directory=[%s] file_names=%s.ome.tif "\
			"output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] "\
			"regression_threshold=0.30 max/avg_displacement_threshold=2.50 "\
			"absolute_displacement_threshold=3.50 compute_overlap "\
			"computation_parameters=[Save memory (but be slower)] "%(gridX,gridY,tiles_dir,tile_name))
	
def write_tiles(r,tiles_dir,theT,channels,sizeZ,meta,outputfile):

	p = 0
	IJ.log("Writing tile %s: %s"%(theT,outputfile))
	writer = ImageWriter()
	writer.setCompression('LZW')
	writer.setMetadataRetrieve(meta)
	writer.setId(outputfile)
	for theC in channels:
		for theZ in range(sizeZ):
			writer.saveBytes(p,r.openBytes(r.getIndex(theZ, theC, theT)))
			p += 1
	writer.close()

def set_metadata(inputMeta,outputMeta,channels):

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
	outputMeta.setPixelsSizeC(inputMeta.getPixelsSizeC(0),0)
	outputMeta.setPixelsSizeT(PositiveInteger(1),0)

	sizeZ = inputMeta.getPixelsSizeZ(0).getValue()
	sizeC = inputMeta.getPixelsSizeC(0).getValue()
	sizeT = inputMeta.getPixelsSizeT(0).getValue()
	for c,chan in enumerate(channels):
		outputMeta.setChannelID("Channel:0:" + str(c), 0, c)
		spp = chan['spp']
		outputMeta.setChannelSamplesPerPixel(spp, 0, c)
		name = chan['name']
		color = chan['color']
		outputMeta.setChannelName(name,0,c)
		outputMeta.setChannelColor(color,0,c)
	
	return outputMeta

def get_reader(file, inputMeta):
	options = ImporterOptions()
	options.setId(file)
	#imps = BF.openImagePlus(options)
	reader = ImageReader()
	reader.setMetadataStore(inputMeta)
	reader.setId(file)
	return reader

def run_script(input_dir,gridX,gridY):
	input_path = glob.glob("%s*.tiff"%input_dir)[0]
	sep = os.path.sep
	inputMeta = MetadataTools.createOMEXMLMetadata()
	reader = get_reader(input_path,inputMeta)
	
	tiles_dir = os.path.join(input_dir,"tiles%s"%sep)
	os.makedirs(tiles_dir)
	sizeZ = inputMeta.getPixelsSizeZ(0).getValue()
	sizeC = inputMeta.getPixelsSizeC(0).getValue()

	channels = []
	chan_d = {}
	for c in range(sizeC):
		chan_d['spp'] = inputMeta.getChannelSamplesPerPixel(0,c)
		chan_d['name'] = inputMeta.getChannelName(0,c)
		chan_d['color'] = inputMeta.getChannelColor(0,c)
		channels.append(chan_d)

	planeCount = sizeZ * sizeC
	if planeCount > 100:
		# write separate channels and stitch separately
		for theC in range(sizeC):
			outputMeta = MetadataTools.createOMEXMLMetadata()
			channel_to_write = [channels[theC]]
			set_metadata(inputMeta,outputMeta,channel_to_write)
			sizeT = inputMeta.getPixelsSizeT(0).getValue()
			for theT in range(sizeT):
				outputfile = "%stile_%s_channel_%s.ome.tif"%(tiles_dir,theT,theC)
				write_tiles(reader,tiles_dir,theT,[theC],sizeZ,outputMeta,outputfile)
				
		last_tile = tiles_dir + 'tile_%s_channel%s.ome.tif'%(sizeT-1,sizeC-1)
		print last_tile
		while not os.path.exists(last_tile):
   			time.sleep(1)
   			
		reader.close()
		for theC in range(sizeC):
			tile_name = "tile_{i}_channel_%s"%theC
			run_stitching(tiles_dir,tile_name,gridX,gridY)
			write_fused(input_dir,outputMeta)
			delete_tiles(tiles_dir)
		
   	else:
   		outputMeta = MetadataTools.createOMEXMLMetadata()
   		set_metadata(inputMeta,outputMeta,channels)
		sizeT = inputMeta.getPixelsSizeT(0).getValue()
		for theT in range(sizeT):
			outputfile = "%stile_%s.ome.tif"%(tiles_dir,theT)
			write_tiles(reader,tiles_dir,theT,range(len(channels)),sizeZ,outputMeta,outputfile)
				
		last_tile = tiles_dir + 'tile_%s.ome.tif'%(sizeT-1)
		print last_tile
		while not os.path.exists(last_tile):
   			time.sleep(1)   	
   			
		reader.close()
		tile_name = "tile_{i}"
		run_stitching(tiles_dir,tile_name,gridX,gridY)
		write_fused(input_dir,outputMeta)
		delete_tiles(tiles_dir)

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
		
	gd.addDirectoryField("directory", "", 50)
	
	gd.showDialog()
	if (gd.wasCanceled()): return
		
	parameters['gridX'] = int(math.ceil(gd.getNextNumber()))
	parameters['gridY'] = int(math.ceil(gd.getNextNumber()))
	
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

	run_script(input_dir,gridX,gridY)