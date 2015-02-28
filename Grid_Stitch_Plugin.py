import sys
import os
import time
import math

import ij
from ij import IJ
from ij import ImageStack, ImagePlus
from ij.io import OpenDialog
from ij.process import ShortProcessor

from loci.plugins import BF
from loci.plugins.in import ImporterOptions
from loci.formats import ImageReader,ImageWriter
from loci.formats import MetadataTools
from loci.common import DataTools

from ome.xml.meta import OMEXMLMetadata
from ome.xml.model.primitives import PositiveInteger,PositiveFloat
from ome.xml.model.enums import DimensionOrder, PixelType

from java.lang import StringBuffer

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
	
def run_stitching(tiles_dir):
	IJ.run("Grid/Collection stitching")

def write_tiles(r,tiles_dir,theT,sizeC,sizeZ,meta):
	writer = ImageWriter()
	writer.setCompression('LZW')
	writer.setMetadataRetrieve(meta)
	writer.setId("%s/tile_%s.ome.tif"%(tiles_dir,theT))
	planes = sizeZ * sizeC
	p = 0
	for theZ in range(sizeZ):
		for theC in range(sizeC):
			writer.saveBytes(p,r.openBytes(reader.getIndex(theZ, theC, theT)))
			p += 1
	writer.close()

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

def get_path():
	od = OpenDialog("Choose Spinning disk  file", None)
	srcDir = od.getDirectory()
	if srcDir is None:
		# User canceled the dialog
		sys.exit(0)
	file = os.path.join(srcDir, od.getFileName())
	return srcDir,file

def run_script():

	input_dir,input_path = get_path()

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
		last_tile = tiles_dir + 'tile_%s.ome.tif'%(sizeT-1)
		while not os.path.exists(last_tile):
   			time.sleep(1)
	reader.close()
	run_stitching(tiles_dir)
	write_fused(tiles_dir,outputMeta)

if __name__=='__main__':

	run_script()