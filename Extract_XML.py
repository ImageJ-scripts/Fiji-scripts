import os
import xml.etree.ElementTree as etree

import ij
from loci.formats import ImageReader
from loci.formats import MetadataTools

def get_reader(file, complete_meta):
	reader = ImageReader()
	reader.setMetadataStore(complete_meta)
	reader.setId(file)
	return reader

# files is a comma separated list of paths to the first ztc
basepath = "/Users/uqdmatt2/Desktop/"	
files = [basepath+"Original_File/example stitch_Z0_T0_C0.tiff"]

for fpath in files:
	original_metadata = MetadataTools.createOMEXMLMetadata()
	reader = get_reader(fpath,original_metadata)
	reader.close()
	xml_data = original_metadata.dumpXML()

	outputdir = os.path.dirname(fpath)
	shortname = os.path.basename(fpath)[:-5]	
	outputpath = os.path.join(outputdir,shortname+".xml")
	root = etree.fromstring(xml_data.decode('utf-8','ignore'))
	et = etree.ElementTree(root)
	et.write(outputpath)

