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
	print glob.glob("%s/*" % tiles_dir)
	try:
		for name in glob.glob("%s/*" % tiles_dir):
			os.remove(name)
		
		shutil.rmtree(tiles_dir)
	except:
		pass 

def write_fused(output_path,meta):
	imp = ij.WindowManager.getCurrentImage()
	meta.setPixelsSizeX(PositiveInteger(imp.getWidth()),0)
	meta.setPixelsSizeY(PositiveInteger(imp.getHeight()),0)
	writer = ImageWriter()
	writer.setCompression('LZW')
	writer.setMetadataRetrieve(meta)
	writer.setId("%s/fused.ome.tif"%output_path)
	littleEndian = not writer.getMetadataRetrieve().getPixelsBinDataBigEndian(0, 0)
	planes = imp.getStack()
	for p in range(planes.getSize()):
		proc = planes.getProcessor(p+1)
		writer.saveBytes(p,DataTools.shortsToBytes(proc.getPixels(), littleEndian))
	writer.close()
	
def run_stitching(tiles_dir,gridX, gridY):
	IJ.run("Grid/Collection stitching", "type=[Grid: snake by rows] order=[Right & Down                ] "\
			"grid_size_x=%s grid_size_y=%s tile_overlap=20 first_file_index_i=0 "\
			"directory=%s file_names=tile_{i}.ome.tif "\
			"output_textfile_name=TileConfiguration.txt fusion_method=[Linear Blending] "\
			"regression_threshold=0.30 max/avg_displacement_threshold=2.50 "\
			"absolute_displacement_threshold=3.50 compute_overlap "\
			"computation_parameters=[Save memory (but be slower)] "\
			"image_output=[Fuse and display]"%(gridX,gridY,tiles_dir))


def write_tiles(r,tiles_dir,theT,sizeC,sizeZ,meta):
	writer = ImageWriter()
	writer.setCompression('LZW')
	writer.setMetadataRetrieve(meta)
	filename = "%s/tile_%s.ome.tif"%(tiles_dir,theT)
	writer.setId(filename)
	planes = sizeZ * sizeC
	p = 0
	for theZ in range(sizeZ):
		for theC in range(sizeC):
			writer.saveBytes(p,r.openBytes(r.getIndex(theZ, theC, theT)))
			p += 1
	writer.close()
	IJ.log("Writing tile %s: %s"%(theT,filename))

def set_metadata(inputMeta,outputMeta):

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
	for c in range(sizeC):
		outputMeta.setChannelID("Channel:0:" + str(c), 0, c);
		spp = inputMeta.getChannelSamplesPerPixel(0,c)
		outputMeta.setChannelSamplesPerPixel(spp, 0, c);
		name = inputMeta.getChannelName(0,c)
		color = inputMeta.getChannelColor(0,c)
		outputMeta.setChannelName(name,0,c)
		outputMeta.setChannelColor(color,0,c)
	
	return outputMeta

def get_reader(file, inputMeta):
	options = ImporterOptions()
	options.setId(file)
	imps = BF.openImagePlus(options)
	reader = ImageReader()
	reader.setMetadataStore(inputMeta)
	reader.setId(file)
	return reader

def run_script(input_dir,gridX,gridY):
	input_path = glob.glob("%s/*.tiff"%input_dir)[0]
	inputMeta = MetadataTools.createOMEXMLMetadata()
	outputMeta = MetadataTools.createOMEXMLMetadata()
	reader = get_reader(input_path,inputMeta)
	outputMeta = set_metadata(inputMeta,outputMeta)

	tiles_dir = os.path.join(input_dir,"tiles")
	if not os.path.exists(tiles_dir):
		os.makedirs(tiles_dir)
		sizeZ = inputMeta.getPixelsSizeZ(0).getValue()
		sizeC = inputMeta.getPixelsSizeC(0).getValue()
		sizeT = inputMeta.getPixelsSizeT(0).getValue()
		for theT in range(sizeT):
			write_tiles(reader,tiles_dir,theT,sizeC,sizeZ,outputMeta)
		last_tile = tiles_dir + '/tile_%s.ome.tif'%(sizeT-1)
		print last_tile
		while not os.path.exists(last_tile):
   			time.sleep(1)
	reader.close()
	run_stitching(tiles_dir,gridX,gridY)
	write_fused(input_dir,outputMeta)
	delete_tiles(tiles_dir)

def make_dialog():

	parameters = {}

	gd = GenericDialogPlus("Grid Stitch SDC Data")
		
	gd.addNumericField("grid_size_x", 3, 0)
	gd.addNumericField("grid_size_y", 3, 0)
		
	gd.addDirectoryField("directory", "", 50)
	
	gd.showDialog()
	if (gd.wasCanceled()): return
		
	parameters['gridX'] = int(math.ceil(gd.getNextNumber()))
	parameters['gridY'] = int(math.ceil(gd.getNextNumber()))
		
	parameters['directory'] = gd.getNextString()
	if parameters['directory'] is None:
	# User canceled the dialog
		return None

	return parameters

if __name__=='__main__':

	params = make_dialog()

	input_dir = params['directory']
	gridX = params['gridX']
	gridY = params['gridY']

	run_script(input_dir,gridX,gridY)