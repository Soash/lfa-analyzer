#@ ImagePlus imp
from ij import IJ, ImagePlus
from ij.gui import PointRoi
from jarray import array
from mpicbg.models import HomographyModel2D, PointMatch, Point
from mpicbg.ij import InverseTransformMapping
import math

def run_crop():
    roi = imp.getRoi()
    
    # Validate that points are selected
    if roi is None or not isinstance(roi, PointRoi):
        IJ.error("Perspective Crop", "Please click exactly 4 points using the Multi-point Tool.")
        return

    poly = roi.getPolygon()
    if poly.npoints != 4:
        IJ.error("Perspective Crop", "Please click exactly 4 points. You clicked " + str(poly.npoints) + ".")
        return

    x = poly.xpoints
    y = poly.ypoints

    # Calculate output width and height
    def dist(x1, y1, x2, y2):
        return math.sqrt((x2-x1)**2 + (y2-y1)**2)

    w1 = dist(x[0], y[0], x[1], y[1])
    w2 = dist(x[3], y[3], x[2], y[2])
    out_w = int(round(max(w1, w2)))

    h1 = dist(x[0], y[0], x[3], y[3])
    h2 = dist(x[1], y[1], x[2], y[2])
    out_h = int(round(max(h1, h2)))

    # Fiji's mpicbg Point class requires Java double arrays
    def make_point(px, py):
        return Point(array([float(px), float(py)], 'd'))

    # Define the source points (clicked on the image)
    p1 = make_point(x[0], y[0])  # Top-Left
    p2 = make_point(x[1], y[1])  # Top-Right
    p3 = make_point(x[2], y[2])  # Bottom-Right
    p4 = make_point(x[3], y[3])  # Bottom-Left

    # Define the target points (perfect rectangle)
    t1 = make_point(0, 0)
    t2 = make_point(out_w, 0)
    t3 = make_point(out_w, out_h)
    t4 = make_point(0, out_h)

    # Create matches mapping Source -> Target
    matches = [
        PointMatch(p1, t1),
        PointMatch(p2, t2),
        PointMatch(p3, t3),
        PointMatch(p4, t4)
    ]

    # Fit the homography model
    model = HomographyModel2D()
    try:
        model.fit(matches)
    except Exception as e:
        IJ.error("Perspective Crop", "Could not calculate perspective transform.")
        return

    # Create the new image and apply the inverse transform mapping
    out_ip = imp.getProcessor().createProcessor(out_w, out_h)
    mapping = InverseTransformMapping(model)
    mapping.mapInterpolated(imp.getProcessor(), out_ip)

    from ij.io import SaveDialog

    # Show the final cropped result
    out_imp = ImagePlus("Cropped Perspective", out_ip)
    out_imp.show()

    # Automatically open a Save dialog
    sd = SaveDialog("Save Cropped Image", "cropped_result", ".png")
    directory = sd.getDirectory()
    filename = sd.getFileName()

    # If the user didn't hit 'Cancel', save the file
    if directory is not None and filename is not None:
        filepath = directory + filename
        IJ.saveAs(out_imp, "PNG", filepath)
        IJ.log("Saved perfectly cropped image to: " + filepath)

run_crop()