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
			"directory=[%s] file_names=[%s] "\
			"output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] "\
			"regression_threshold=0.30 max/avg_displacement_threshold=2.50 "\
			"absolute_displacement_threshold=3.50 compute_overlap "\
			"computation_parameters=[Save memory (but be slower)] "\
			"image_output=[Write to disk] output_directory=%s"%(gridX,gridY,tiles_dir,tile_name,tiles_dir))

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
	return meta.getPixelsSizeT(0).getValue()

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
	first = [s for s in input_data if "Z00_T0_C0" in s][0]
	sep = os.path.sep

	original_metadata = []
	for filename in input_data:
		meta = MetadataTools.createOMEXMLMetadata()
		reader = get_reader(filename,meta)
		original_metadata.append(meta)
		reader.close()

	complete_meta = original_metadata[0]
	channels = channel_info(complete_meta)
	num_tiles = tile_info(complete_meta)
	for t in range(num_tiles):
		for c,chan in enumerate(channels):
			frag = "Z00_T%s_C%s"%(t,c)
			input_path = [s for s in input_data if frag in s][0]
			tile_meta = MetadataTools.createOMEXMLMetadata()
			tile_meta = set_metadata(complete_meta,tile_meta,chan)
			replace_meta(tile_meta,input_path)

	idx = input_data[0].index("Z00_T0_C0.tiff")
	prefix = input_data[0][:idx]
	for filename in input_data:
		os.rename(filename,input_dir+filename[idx:])
		
	if select_channel:
		tile_names = "Z00_T{i}_C%s.tiff"%channel
		run_stitching(input_dir,tile_names,gridX,gridY)
	else:
		for theC in range(len(channels)):
			tile_names = "Z00_T{i}_C%s.tiff"%theC
			run_stitching(input_dir,tile_names,gridX,gridY)

	# restore original metadata and filename to tiles
	rewritten_data = glob.glob("%s*.tiff"%input_dir)
	for f,filename in enumerate(rewritten_data):
		replace_meta(original_metadata[f],filename)
		os.rename(filename,prefix+os.path.basename(filename))
		
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
