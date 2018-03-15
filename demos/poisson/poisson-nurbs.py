"""
Approximating a manufactured solution to the Poisson equation.

This example uses NURBS geometry generated by igakit.
"""

from tIGAr import *
from tIGAr.NURBS import *
from igakit.nurbs import NURBS as NURBS_ik
from igakit.io import PetIGA
from numpy import array
import math

####### Geometry creation #######

# Parameter determining level of refinement
REF_LEVEL = 6

if(mpirank==0):
    print("Creating geometry with igakit...")

# Open knot vectors for a one-Bezier-element bi-unit square.
uKnots = [-1.0,-1.0,-1.0,1.0,1.0,1.0]
vKnots = [-1.0,-1.0,-1.0,1.0,1.0,1.0]

# Array of control points, for a bi-unit square with the interior
# parameterization distorted.
cpArray = array([[[-1.0,-1.0],[0.0,-1.0],[1.0,-1.0]],
                  [[-1.0,0.0],[0.7,0.3],[1.0,0.0]],
                  [[-1.0,1.0],[0.0,1.0],[1.0,1.0]]])

# Create initial mesh
ikNURBS = NURBS_ik([uKnots,vKnots],cpArray)

# Refinement
numNewKnots = 1
for i in range(0,REF_LEVEL):
    numNewKnots *= 2
h = 2.0/float(numNewKnots)
numNewKnots -= 1
knotList = []
for i in range(0,numNewKnots):
    knotList += [float(i+1)*h-1.0,]
newKnots = array(knotList)
ikNURBS.refine(0,newKnots)
ikNURBS.refine(1,newKnots)

# Output in PetIGA format
if(mpirank==0):
    PetIGA().write("out.dat",ikNURBS)
MPI.barrier(mycomm)

####### Preprocessing #######

if(mpirank==0):
    print("Generating extraction...")

# Read in the generated geometry to create a control mesh.
splineMesh = NURBSControlMesh("out.dat",useRect=True)

# Alternative:  Create splineMesh directly from ikNURBS:
#NURBSControlMesh(ikNURBS,useRect=True)

# Create a spline generator for a spline with a single scalar field on the
# given control mesh, where the scalar field is the same as the one used
# to determine the mapping $\mathbf{F}:\widehat{\Omega}\to\Omega$.
splineGenerator = EqualOrderSpline(1,splineMesh)

# Set Dirichlet boundary conditions on the 0-th (and only) field, on both
# ends of the domain, in both directions, for two layers of control points.
# This strongly enforces BOTH $u=0$ and $\nabla u\cdot\mathbf{n}=0$. 
field = 0
scalarSpline = splineGenerator.getScalarSpline(field)
for parametricDirection in [0,1]:
    for side in [0,1]:
        sideDofs = scalarSpline.getSideDofs(parametricDirection,side)
        splineGenerator.addZeroDofs(field,sideDofs)

# Write extraction data to the filesystem.
DIR = "./extraction"
splineGenerator.writeExtraction(DIR)

####### Analysis #######

if(mpirank==0):
    print("Setting up extracted spline...")

# Choose the quadrature degree to be used throughout the analysis.
QUAD_DEG = 4

# Create the extracted spline directly from the generator.
# As of version 2017.2, this is required for using quad/hex elements in
# parallel.
spline = ExtractedSpline(splineGenerator,QUAD_DEG)

# Alternative: Can read the extracted spline back in from the filesystem.
# For quad/hex elements, in version 2017.2, this only works in serial.

#spline = ExtractedSpline(DIR,QUAD_DEG)


if(mpirank==0):
    print("Solving...")

# The trial function.  The function rationalize() creates a UFL Division
# object which is the quotient of the homogeneous representation of the
# function and the weight field from the control mesh.
u = spline.rationalize(TrialFunction(spline.V))

# Corresponding test function.
v = spline.rationalize(TestFunction(spline.V))

# Create a force, f, to manufacture the solution, soln
x = spline.spatialCoordinates()
soln = sin(pi*x[0])*sin(pi*x[1])
f = -spline.div(spline.grad(soln))

# Set up and solve the Poisson problem
res = inner(spline.grad(u),spline.grad(v))*spline.dx - inner(f,v)*spline.dx

# FEniCS Function objects are always in the homogeneous representation; it
# is a good idea to name variables in such a way as to recall this.
u_homo = Function(spline.V)
spline.solveLinearVariationalProblem(res,u_homo)


####### Postprocessing #######

# The solution, u, is in the homogeneous representation.
u_homo.rename("u","u")
File("results/u.pvd") << u_homo

# To visualize correctly in Paraview, we need the geometry information as well.
nsd = 3
for i in range(0,nsd+1):
    name = "F"+str(i)
    spline.cpFuncs[i].rename(name,name)
    File("results/"+name+"-file.pvd") << spline.cpFuncs[i]

# Useful notes for plotting:
#
#  In Paraview, the data in these different files can be combined with the
#  Append Attributes filter, then an appropriate vector field for the mesh
#  warping and the weighted solution can be created using the Calculator
#  filter.  E.g., in this case, the vector field to warp by would be
#
#   (F0/F3 - coordsX)*iHat + (F1/F3 - coordsY)*jHat + (F2/F3 - coordsZ)*kHat
#
#  in Paraview Calculator syntax, and the solution would be u/F3.

# Compute and print the $L^2$ error in the discrete solution.
L2_error = math.sqrt(assemble(((spline.rationalize(u_homo)-soln)**2)
                              *spline.dx))

if(mpirank==0):
    print("L2 Error = "+str(L2_error))
