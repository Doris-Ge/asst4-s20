#!/usr/bin/python

# Code for generating and reading graphrat mazes
# Parameters:
# tree: Tree defining partitioning into regions
# k: Expansion factor scaling tree regions into grid regions


import getopt
import sys
import math
import string
import datetime
import fractal

import rutil

def usage(name):
    print("Usage: %s [-h][-S][-r] -t TFILE [-E E] [-l L:H] [-o OUT] [-s SEED]" % name)
    print("\t-h        Print this message")
    print("\t-r        Include regions in graph file")
    print("\t-S        Generate SVG representation of graph")
    print("\t-E E      Expansion factor for tree regions to grid regions")
    print("\t-t TFILE  Fractal tree file")
    print("\t-l L:H Specify range of ideal load factors")
    print("\t-o OUT Specify output file")
    sys.exit(0)

class RatMode:
    # Different options for specifying initial rat state
    (random, uniform, diagonal, center) =  range(4)
    modeNames = ["random", "uniform", "diagonal", "center"]

class Region:
    graph = None # Underlying graph
    rid = 0  # Region ID
    x = 0  # Left X
    y = 0  # Upper Y
    w = 0  # Width
    h = 0  # Height
    zoneId = None  # Zone ID

    def __init__(self, g, r, x, y, w, h, zid = None):
        self.graph = g
        self.rid = r
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        if zid is not None:
            self.zoneId = zid
            
    def nodeCount(self):
        return self.w * self.h

    def edgeCount(self):
        ncount = self.nodeCount()
        # Grid edges
        ecount = 4 * ncount
        hcount = len(self.graph.hubList(self.x, self.y, self.w, self.h))
        # Complete graph among hubs
        ecount += hcount * (hcount - 1)
        # Connection by hub to/from every other node, except for grid neighbors and hubs
        ecount += 2 * hcount * (ncount - 4 - hcount)
        # Deduct for lack of edges along graph boundary
        if self.x == 0:
            ecount -= self.h
        if self.x + self.w == self.graph.width:
            ecount -= self.h        
        if self.y == 0:
            ecount -= self.w
        if self.y + self.h == self.graph.height:
            ecount -= self.w
        return ecount
    

class Graph:
    errorLimit = 5
    # How many hubs to insert into nonsquare regions
    maxHubs = 3
    # What is the minimum aspect ratio for inserting multiple hubs
    minAspect = 2.0
    errorCount = 0
    tree = None
    expansion = 1
    width = 0
    height = 0
    edges = {}  # Maps edges to True.  Include both directions
    commentList = []  # Documentation about how generated
    nodeList = [] # Node ideal load factors
    ilfRange = (1.2,1.8) # Range of ideal load factors
    rng = None
    # Optional list of regions for output file.
    regionList = [] 
    # Stuff related to SVG generation
    svgHeader = 'xmlns="http://www.w3.org/2000/svg"' # A blurb that should be at the start of an SVG file
    # Background colors
    svgColors = ["blanchedalmond", "lightgreen", "lightsteelblue", "palegoldenrod",
                 "plum", "lightcyan", "peru", "sandybrown", "lightpink",
                 "lavender", "honeydew", "thistle"]
    # Text color
    svgTextColor = "indigo"

    def __init__(self):
        self.clear()

    def clear(self):
        self.width = 0
        self.height = 0
        self.edges = {}
        self.commentList = []
        self.nodeList = []
        self.errorCount = 0
        self.tree = None
        self.expansion = 1
        self.regionList = []

    def generate(self, tree, expansion = 1, ilf = None, seed = rutil.DEFAULTSEED, doRegion = False):
        self.clear()
        self.rng = rutil.RNG([seed])
        self.tree = tree
        self.expansion = expansion
        if ilf is not None:
            self.ilfRange = ilf
        self.commentList = []
        self.regionList = []
        tgen = datetime.datetime.now()
        self.commentList.append("Generated %s" % tgen.ctime())
        self.commentList.append("Parameters: expansion = %d, ilf = (%.2f,%.2f)" % (expansion, self.ilfRange[0], self.ilfRange[1]))
        self.commentList.append("Region tree structure")
        self.commentList += tree.headerList()
        self.width = expansion * tree.root.width
        self.height = expansion * tree.root.height
        nodeCount = self.width * self.height
        self.nodeList = [self.assignIlf(i) for i in range(nodeCount)]
        self.edges = {}
        # Generate grid edges
        errCount = 0
        for r in range(self.height):
            for c in range(self.width):
                own = self.id(r, c)
                north = self.id(r-1, c)
                if north >= 0:
                    self.addEdge(own, north)
                south = self.id(r+1, c)
                if south >= 0:
                    self.addEdge(own, south)
                west = self.id(r, c-1)
                if west >= 0:
                    self.addEdge(own, west)
                east = self.id(r, c+1)
                if east >= 0:
                    self.addEdge(own, east)
                if self.errorCount > self.errorLimit:
                    fractal.errorMessage("... generate: Too many errors (r = %d, c = %d)" % (r,c))
                    return

        rid = 0
        for n in tree.leafList():
            rwidth = n.width   * expansion
            rheight = n.height * expansion
            rleftX = n.leftX   * expansion
            rupperY = n.upperY * expansion
            if doRegion:
                self.regionList.append(Region(self, rid, rleftX, rupperY, rwidth, rheight))
                rid += 1
            self.makeHub(rleftX, rupperY, rwidth, rheight)
            if self.errorCount > self.errorLimit:
                return


    def hubList(self, x, y, w, h):
        cx = x + w//2
        cy = y + h//2
        hlist = [(cx,cy)]
        dx = w//(self.maxHubs+1)
        dy = h//(self.maxHubs+1)
        if w >= self.minAspect * h and w > self.maxHubs and dx > 1:
            # Multiple hubs along X axis
            hlist = [(x+(i+1)*dx,cy) for i in range(self.maxHubs)]
        if h >= self.minAspect * w and h > self.maxHubs and dy > 1:
            # Multiple hubs along Y axis
            hlist = [(cx,y+(i+1)*dy) for i in range(self.maxHubs)]
        return hlist


    def makeHub(self, x, y, w, h):
        hlist = self.hubList(x, y, w, h)
        for cx, cy in hlist:
            cid = self.id(cy, cx)
            for j in range(w):
                for i in range(h):
                    id = self.id(y+i, x+j)
                    self.addEdge(cid, id)
                    if self.errorCount > self.errorLimit:
                        fractal.errorMessage("... makeHub.  Too many errors x = %d, y = %d, w = %d, h = %d" % (x, y, w, h))
                        return
        
    # Load graph from file
    def load(self, fname = ""):
        self.clear()
        if fname == "":
            f = sys.stdin
        else:
            try:
                f = open(fname, "r")
            except:
                fractal.errorMessage("Could not open file '%s'" % fname)
                return False
        expectedEgeCount = 0
        expectedNodeCount = 0
        expectedRegionCount = 0
        realEdgeCount = 0
        realNodeCount = 0
        realRegionCount = 0
        for line in f:
            if fractal.isComment(line):
                continue
            args = line.split()
            cmd = args[0]
            # Header information
            if self.width == 0:
                ifields = []
                if len(args) < 3 or len(args) > 4:
                    fractal.errorMessage("Invalid header line '%s'" % line)
                    return False
                try:
                    ifields = [int(s) for s in args]
                except:
                    fractal.errorMessage("Invalid header line '%s'" % line)
                    return False
                self.width = ifields[0]
                self.height = ifields[1]
                expectedEdgeCount = ifields[2]
                expectedNodeCount = self.width * self.height
                expectedRegionCount = ifields[3] if len(args) == 4 else 0
                self.nodeList = [1.5 for i in range(expectedNodeCount)]
            elif cmd == 'n':
                ilf = float(args[1])
                self.nodeList[realNodeCount] = ilf
                realNodeCount += 1
            elif cmd == 'e':
                i = int(args[1])
                j = int(args[2])
                if self.addEdge(i,j):
                    # Since addEdge puts both (i,j) and (j,i) into set, only half of the
                    # edges will return True from addEdge
                    realEdgeCount += 2 
            elif cmd == 'r':
                x, y, w, h = [int(s) for s in args[1:]]
                r = Region(self, realRegionCount, x, y, w, h)
                self.regionList.append(r)
                realRegionCount += 1
            else:
                fractal.errorMessage("Couldn't read graph file '%s'.  Invalid line: '%'" % fname, fractal.trim(line))
                self.clear()
                return False
        if fname is not None:
            f.close()
        if realNodeCount != expectedNodeCount:
            fractal.errorMessage("Couldn't read graph file '%s'.  Expected %d nodes.  Found %d" % (fname, expectedNodeCount, realNodeCount))
            return False
        if realEdgeCount != expectedEdgeCount:
            fractal.errorMessage("Couldn't read graph file '%s'.  Expected %d edges.  Found %d" % (fname, expectedEdgeCount, realEdgeCount))
            return False
        if realRegionCount != expectedRegionCount:
            fractal.errorMessage("Couldn't read graph file '%s'.  Expected %d regions.  Found %d" % (fname, expectedRegionCount, realRegionCount))
            return False
        else:
            fractal.infoMessage("Read %d X %d graph with %d edges" % (self.width, self.height, realEdgeCount))
            return True
 
    def id(self, r, c):
        if r < 0 or r >= self.height:
            return -1
        if c < 0 or c >= self.width:
            return -1
        return r * self.width + c

    def rowColumn(self, id):
        r = id//self.width
        c = id - r*self.width
        return (r, c)

    # Set ideal load factor
    def assignIlf(self, id):
        delta = self.ilfRange[1] - self.ilfRange[0]
        return self.ilfRange[0] + self.rng.randFloat(delta)

    def addEdge(self, i, j):
        nodeCount = len(self.nodeList)
        if i < 0 or i >= nodeCount:
            fractal.errorMessage("Invalid from node id %d" % i)
            self.errorCount += 1
        if j < 0 or j >= nodeCount:
            fractal.errorMessage("Invalid to node id %d" % j)
            self.errorCount += 1
        if i != j and (i,j) not in self.edges:
            self.edges[(i,j)] = True
            self.edges[(j,i)] = True
            return True
        return False
            
    def edgeList(self):
        elist = [e for e in self.edges]
        elist.sort()
        return elist

    # Generate list with entry with each node, giving its degree (including self)
    def degreeList(self):
        result = [1] * len(self.nodeList)
        for e in self.edges:
            idx = e[0]
            result[idx] += 1
        return result

    # Store graph
    def store(self, fname = None):
        if fname is None:
            f = sys.stdout
        else:
            try:
                f = open(fname, "w")
            except:
                fractal.errorMessage("Couldn't open file '%s' for writing" % (fname))
                return False
        elist = self.edgeList()
        if len(self.regionList) == 0:
            fractal.showComments(self.commentList + ["", "Width Height Edges"], f)
            f.write("%d %d %d\n" % (self.width, self.height, len(self.edges)))
        else:
            fractal.showComments(self.commentList + ["", "Width Height Edges Regions"], f)
            f.write("%d %d %d %d\n" % (self.width, self.height, len(self.edges), len(self.regionList)))
        for i in range(len(self.nodeList)):
            f.write("n %d %.5f\n" % (i, self.nodeList[i]))
        for e in elist:
            f.write("e %d %d\n" % e)
        for r in self.regionList:
            f.write("r %d %d %d %d\n" % (r.x, r.y, r.w, r.h))
        if fname != "":
            f.close()
        return True

    def svgGrid(self, width, height, outfile, scaleFactor = 1):
        # Vertical lines
        for x in range(width+1):
            xs = x * scaleFactor
            ys = height * scaleFactor
            outfile.write('<line x1="%d" y1="0" x2="%d" y2="%d" stroke="gray" strokeWidth="1"/>\n' %
                          (xs, xs, ys))
        # Horizontal lines
        for y in range(height+1):
            xs = width * scaleFactor
            ys = y * scaleFactor
            outfile.write('<line x1="0" y1="%d" x2="%d" y2="%d" stroke="gray" strokeWidth="1"/>\n' %
                          (ys, xs, ys))

    def svgRectangle(self, x, y, width, height, lineColor, fillColor, outfile, fat = False, scaleFactor = 1):
        vals = [scaleFactor * v for v in [x, y, width, height]]
        strokeWidth = 3 if fat else 1
        outfile.write('<rect x="%d" y="%d" width="%d" height = "%d" stroke = "%s" fill = "%s" stroke-width="%d"/>\n' %
                      (vals[0], vals[1], vals[2], vals[3], lineColor, fillColor, strokeWidth))

    # Write some text in a box where it's unlikely to overlap anything else
    def svgBoxLabel(self, label, x, y, outfile, scaleFactor = 1):
        font = "Arial"
        fsize = 14 
        color = self.svgTextColor
        leftX = x * scaleFactor + 4
        lowerY = y * scaleFactor + 4 + fsize
        outfile.write('<text x="%d" y="%d" style="fill: %s; stroke: none; font-size: %dpx; font-family: %s; font-weight: bold">%s</text>\n' %
                      (leftX, lowerY, color, fsize, font, str(label)))

    # Generate SVG file showing grid + regions
    def toSvg(self, fname, gridSpacing = 5):
        try:
            outfile = open(fname, 'w')
        except Exception as ex:
            print("Can't open file '%s' (%s)" % (fname, str(ex)))
            return
        # Preamble
        outfile.write('<svg width="%d" height="%d" %s>\n' % (self.width*gridSpacing, self.height*gridSpacing, self.svgHeader))
        # Draw any background coloring of regions
        for region in self.regionList:
            zid = region.zoneId
            if zid is None:
                continue
            rx, ry, rw, rh = (region.x, region.y, region.w, region.h)
            idx = zid % len(self.svgColors)
            color = self.svgColors[idx]
            self.svgRectangle(rx, ry, rw, rh, "none", color,
                              outfile, scaleFactor = gridSpacing, fat = False)
        # Draw grid
        self.svgGrid(self.width, self.height, outfile, gridSpacing)
        for region in self.regionList:
            rid = region.rid
            rx, ry, rw, rh = (region.x, region.y, region.w, region.h)
            self.svgRectangle(rx, ry, rw, rh, "black", "none",
                              outfile, scaleFactor = gridSpacing, fat = True)
            self.svgBoxLabel(str(rid), rx, ry, outfile, gridSpacing)
            hlist = self.hubList(rx, ry, rw, rh)
            for cx, cy in hlist:
                self.svgRectangle(cx, cy, 1, 1, "lightgray", "red", outfile, scaleFactor = gridSpacing)
        # Draw graph bounding box
        self.svgRectangle(0, 0, self.width, self.height, "black", "none", outfile, scaleFactor = gridSpacing, fat = True)
        # Finish
        outfile.write("</svg>\n")
        outfile.close()
            

    # Generate rats for graph and write to file
    def makeRats(self, fname = "", mode = RatMode.uniform, load = 1, seed = rutil.DEFAULTSEED):
        nodeCount = self.width * self.height
        clist = []
        tgen = datetime.datetime.now()
        clist.append("# Generated %s" % tgen.ctime())
        clist.append("# Parameters: load = %d, mode = %s, seed = %d" % (load, RatMode.modeNames[mode], seed))
        rng = rutil.RNG([seed])
        if fname == "":
            f = sys.stdout
        else:
            try:
                f = open(fname, "w")
            except:
                "Couldn't open output file '%s'"
                return False
        rlist = []
        if mode == RatMode.uniform:
            rlist = range(nodeCount)
        elif mode == RatMode.diagonal:
            if self.width >= self.height:
                aspect = float(self.height)/self.width
                for c in range(self.width):
                    r = int(aspect * c)
                    rlist.append(self.id(r,c))
            else:
                aspect = float(self.width)/self.height
                for r in range(self.height):
                    c = int(aspect * r)
                    rlist.append(self.id(r,c))
        elif mode == RatMode.center:
            r = self.height // 2
            c = self.width  // 2
            rlist = [self.id(r,c)]
        elif mode == RatMode.random:
            pass
        else:
            fractal.errorMessage("makeRats: Invalid rat mode (%d)" % mode)
            return False
        ratCount = nodeCount * load
        if mode == RatMode.random:
            fullRlist = [self.rng.randInt(0, nodeCount-1) for r in range(ratCount)]
        else:
            factor = ratCount // len(rlist)
            fullRlist = rlist * factor
            fullRlist = self.rng.permute(fullRlist)
        # Print it out
        f.write("%d %d\n" % (nodeCount, len(fullRlist)))
        for c in clist:
            f.write(c + '\n')
        for id in fullRlist:
            f.write("%d\n" % id)
        if fname != "":
            f.close()
        return True

# Runtime code for graph generation
def run(name, args):
    expansion = 1
    tree = None
    fname = None
    ilf = None
    seed = 418
    storeGraph = True
    doRegion = False
    optlist, args = getopt.getopt(args, "hSrE:t:l:o:s:")
    for (opt, val) in optlist:
        if opt == '-h':
            usage(name)
        elif opt == '-E':
            expansion = int(val)
        elif opt == '-S':
            storeGraph = False
        elif opt == '-r':
            doRegion = True
        elif opt == '-t':
            tree = fractal.FractalTree()
            if not tree.loadTree(val):
                return
        elif opt == '-l':
            fields = val.split(':')
            if fields != 2:
                print "Ideal load factor requires two parameters"
                usage(name)
            try:
                lval = float(fields[0])
                hval = float(fields[1])
            except:
                print "Ideal load factor requires two numeric parameters"
                usage(name)
            ilf = (lval, hval)
        elif opt == '-o':
            fname = val
        elif opt == '-s':
            seed = int(val)
    if tree is None:
        print("Cannot generate graph with tree")
        usage(name)
        return
    g = Graph()
    g.generate(tree, expansion, ilf, seed, doRegion)
    if storeGraph:
        g.store(fname = fname)
    else:
        g.toSvg(fname)

if __name__ == "__main__":
    run(sys.argv[0], sys.argv[1:])


        
    
