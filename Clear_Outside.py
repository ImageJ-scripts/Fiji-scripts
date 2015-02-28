import sys
from ij import IJ as ij
from ij.plugin.frame import RoiManager
from ij.gui import Roi, PolygonRoi 

from loci.plugins import BF
from loci.common import Region
from loci.plugins.in import ImporterOptions
from loci.formats import ImageReader, ImageWriter
from loci.formats import MetadataTools
from ome.xml.meta import OMEXMLMetadata

file = "%s"

options = ImporterOptions()
options.setId(file)
imps = BF.openImagePlus(options)

reader = ImageReader()
omeMeta = MetadataTools.createOMEXMLMetadata()
reader.setMetadataStore(omeMeta)
reader.setId(file)

roiCount = omeMeta.getROICount()

if roiCount > 1:
    sys.exit(0)

omeMetaStr =  omeMeta.dumpXML()
shape = omeMeta.getShapeType(0,0)

if 'Polygon' not in shape:
    sys.exit(0)

prefix = omeMetaStr.index(shape)
stop = omeMetaStr.find('/',prefix,-1)    - 1
start = len(shape + " " + "points=") + 1

pts = omeMetaStr[start+prefix:stop]

new_pts_str =pts.replace(" ",",")
new_pts = [int(p) for p in new_pts_str.split(",")]

xs = new_pts[0::2]
ys = new_pts[1::2]

proi = PolygonRoi(xs, ys, len(xs), Roi.POLYGON)  
imp = imps[0]
imp.setRoi(proi)

# create a writer and set metadata
writer = ImageWriter()
writer.setMetadataRetrieve(omeMeta)
writer.setId('%s')

# get the stack
planes = imp.getStack()
for p in range(planes.getSize()):

    # get the plane
    plane = planes.getProcessor(p+1)
    
    # fill outside
    plane.fillOutside(proi)
    
    pixels = plane.convertToByte(True).getPixels()
    writer.saveBytes(p,pixels)
    
reader.close() 
writer.close()
imp.flush()