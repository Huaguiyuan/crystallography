import numpy as np
from numpy import matrix
from numpy import isclose
from numpy import allclose
from numpy.random import random as rand
from numpy.linalg import eig
from numpy.linalg import eigh
from numpy.linalg import det
import math
from math import pi, acos
from math import fabs
from pymatgen.core.operations import SymmOp
from copy import deepcopy
rad = pi/180.
deg = 180./pi

def angle(v1, v2):
    '''
    Calculate the angle (in radians) between two vectors
    '''
    v1 = np.real(v1)
    v2 = np.real(v2)
    dot = np.dot(v1, v2)
    if isclose(dot, 1.0):
        return 0
    elif isclose(dot, -1.0):
        return pi
    return acos(dot / (np.linalg.norm(v1) * np.linalg.norm(v2)))

def random_shear_matrix(width=1.0, unitary=False):
    '''
    Generate a random symmetric shear matrix with Gaussian elements. If unitary
    is True, normalize to determinant 1
    '''
    mat = np.zeros([3,3])
    determinant = 0
    while determinant == 0:
        a, b, c = np.random.normal(scale=width), np.random.normal(scale=width), np.random.normal(scale=width)
        mat = np.array([[1,a,b],[a,1,c],[b,c,1]])
        determinant = np.linalg.det(mat)
    if unitary:
        new = mat / np.cbrt(np.linalg.det(mat))
        return new
    else: return mat

def random_vector(minvec=[0.,0.,0.], maxvec=[1.,1.,1.], width=0.35, unit=False):
    '''
    Generate a random vector for lattice constant generation. The ratios between
    x, y, and z of the returned vector correspond to the ratios between a, b,
    and c. Results in a Gaussian distribution of the natural log of the ratios.
    '''
    vec = np.array([np.exp(np.random.normal(scale=width)), np.exp(np.random.normal(scale=width)), np.exp(np.random.normal(scale=width))])
    if unit:
        return vec/np.linalg.norm(vec)
    else:
        return vec

def is_orthogonal(m, tol=.001):
    #Calculate whether or not a matrix is orthogonal
    m1 = np.dot(m, np.transpose(m))
    m2 = np.dot(np.transpose(m), m)
    if not allclose(m1, np.identity(3), rtol=tol) or not allclose(m2, np.identity(3), rtol=tol):
        return False
    else:
        return True

def aa2matrix(axis, angle, radians=True, random=False):
    '''
    Given an axis and an angle, return a 3x3 rotation matrix
    Based on:
    https://en.wikipedia.org/wiki/Rotation_matrix#Axis_and_angle
    '''
    #Convert to radians if necessary
    if radians is not True:
        angle *= rad
    #Allow for generation of random rotations
    if random is True:
        a = rand()
        axis = [rand(),rand(),rand()]
        angle = rand()*pi*2
    #Ensure axis is a unit vector
    axis = axis / np.linalg.norm(axis)
    #Define quantities which are reused
    x = np.real(axis[0])
    y = np.real(axis[1])
    z = np.real(axis[2])
    c = math.cos(angle)
    s = math.sin(angle)
    C = 1 - c
    #Define the rotation matrix
    Q = np.zeros([3,3])
    Q[0][0] = x*x*C + c
    Q[0][1] = x*y*C - z*s
    Q[0][2] = x*z*C + y*s
    Q[1][0] = y*x*C + z*s
    Q[1][1] = y*y*C + c
    Q[1][2] = y*z*C - x*s
    Q[2][0] = z*x*C - y*s
    Q[2][1] = z*y*C + x*s
    Q[2][2] = z*z*C + c
    return Q

def matrix2aa(m, radians=True):
    '''
    Return the axis and angle from a rotation matrix.
    m must be an orthogonal matrix with determinant 1.
    The axis is an eigenvector with eigenvalue 1.
    The angle is determined by the trace and the asymmetryic part of m.
    Based on:
    https://en.wikipedia.org/wiki/Rotation_matrix#Axis_and_angle
    '''
    if type(m) == SymmOp:
        m = m.rotation_matrix
    #Check if m is the identity matrix
    if allclose(m, np.identity(3)):
        return None, 0.
    if not is_orthogonal(m):
        print("Error: matrix is not orthogonal.")
        return
    #Check that m has posititve determinant
    if not isclose(det(m), 1, rtol=.001):
        print("Error: invalid rotation matrix, determinant is not 1.")
        print("Divide matrix by inversion operation beore calling matrix2aa.")
        return
    #Determine the eigenvector(s) of m
    e = np.linalg.eig(m)
    eigenvalues = e[0]
    possible = np.transpose(e[1])
    eigenvectors = []
    for v in possible:
        if allclose(v, np.dot(m, v)):
            eigenvectors.append(v)
    #Determine the angle of rotation
    if len(eigenvectors) == 1:
        v = eigenvectors[0]
        x = m[2][1] - m[1][2]
        y = m[0][2] - m[2][0]
        z = m[1][0] - m[0][1]
        r = math.sqrt(x**2+y**2+z**2)
        t = m[0][0] + m[1][1] + m[2][2]
        theta = np.arctan2(r, t-1.)
        #Ensure 0<theta<pi
        if theta > pi:
            #Make sure 180 degree rotations are not converted to 0
            if isclose(theta, pi, atol=1e-2, rtol=1e-3):
                theta = pi
            else:
                theta = pi*2 - theta
        if theta < 0:
            theta *= -1
            v *= -1
        #Convert to degrees if necessary
        if radians is not True:
            theta *= deg
        return v, theta
    #If no eigenvectors are found
    elif len(eigenvectors) == 0:
        print("Error: matrix2aa did not find any eigenvectors.")
        return
    #If multiple eigenvectors are found
    elif len(eigenvectors) > 1:
        print("Warning: multiple eigenvectors found.")
        print("Found eigenvectors:")
        print(v)
        return None, 0.

def rotate_vector(v1, v2):
    '''
    Rotates a vector v1 to v2 about an axis perpendicular to both
    Returns the 3x3 rotation matrix used to do so
    '''
    v1 = v1 / np.linalg.norm(v1)
    v2 = v2 / np.linalg.norm(v2)
    dot = np.dot(v1, v2)
    #Handle collinear vectors
    if np.isclose(dot, 1, rtol=.0001):
        return np.identity(3)
    elif np.isclose(dot, -1, rtol=.0001):
        r = [rand(),rand(),rand()]
        v3 = np.cross(v1, r)
        return aa2matrix(v3, pi)
    theta = angle(v1, v2)
    v3 = np.cross(v1, v2)
    return aa2matrix(v3, theta)
        
def are_equal(op1, op2, allow_pbc=True, rtol=1e-3, atol=1e-3):
    #Check two SymmOps for equivalence
    #pbc=True means integer translations will be ignored
    m1 = op1.rotation_matrix
    m2 = op2.rotation_matrix
    #Check that rotations are equivalent
    if not np.allclose(m1, m2, rtol=rtol, atol=atol):
        return False
    v1 = op1.translation_vector
    v2 = op2.translation_vector
    if allow_pbc is False:
        #Check if translation vectors are equal
        if np.allclose(v1, v2, rtol=rtol, atol=atol):
            return True
        else: return False
    elif allow_pbc is True:
        #Check if translation vectors are equal up to integer difference
        difference = v1 - v2
        if np.allclose(difference, np.round(difference), rtol=rtol, atol=atol):
            return True
        else: return False

class OperationAnalyzer(SymmOp):
    '''
    Class for comparing operations. Stores rotation axis, angle, as well as
    the type of operation (identity, inversion, rotation, or rotoinversion).
    By default, takes a SymmOp as argument.
    Note: rotoinversions with odd-order rotational parts will have an over-all
        even order. For example, the order of (-3) is 6.
    Note: reflections are treated as rotoinversions of order 2.
    '''
    #TODO: include support for off-center operations
    #TODO: include support for shear and scaling operations
    #TODO: include support for matrix-column and axis-angle initialization
    def get_order(angle, rotoinversion=False, tol=1e-2):
        #Find the order of a rotation based on its angle
        found = False
        for n in range(1, 61):
            x = (n*angle) / (2.*pi)
            y = x - np.round(x)
            if abs(y) <= tol:
                found = True
                break
        if found is True:
            #Double order of odd-rotation rotoinversions
            if rotoinversion is True:
                if n % 2 == 1:
                    return int(n * 2)
                else:
                    return int(n)
            else:
                return int(n)
        if not found:
            return "irrational"
    
    def __init__(self, op):
        if type(op) == deepcopy(SymmOp):
            self.op = op
            self.tol = op.tol
            self.affine_matrix = op.affine_matrix
            self.m = op.rotation_matrix
            self.det = det(self.m)
        elif (type(op) == np.ndarray) or (type(op) == np.matrix):
            if op.shape == (3,3):
                self.op = SymmOp.from_rotation_and_translation(op, [0,0,0])
                self.m = self.op.rotation_matrix
                self.det = det(op)
        else:
            print("Error: OperationAnalyzer requires a SymmOp or 3x3 array.")
        #If rotation matrix is not orthogonal
        if not is_orthogonal(self.m):
            self.type = "general"
            self.axis, self.angle, self.order, self.rotation_order = None, None, None, None
        #If rotation matrix is orthogonal
        else:
            #If determinant is positive
            if det(self.m) > 0:
                self.inverted = False
                self.axis, self.angle = matrix2aa(self.m)
                if isclose(self.angle, 0):
                    self.type = "identity"
                    self.order = int(1)
                    self.rotation_order = int(1)
                else:
                    self.type = "rotation"
                    self.order = OperationAnalyzer.get_order(self.angle)
                    self.rotation_order = self.order
            #If determinant is negative
            elif det(self.m)< 0:
                self.inverted = True
                mi = self.m * -1
                self.axis, self.angle = matrix2aa(mi)
                if isclose(self.angle, 0):
                    self.type = "inversion"
                    self.order = int(2)
                    self.rotation_order = int(1)
                else:
                    self.axis *= -1
                    self.type = "rotoinversion"
                    self.order = OperationAnalyzer.get_order(self.angle, rotoinversion=True)
                    self.rotation_order = OperationAnalyzer.get_order(self.angle, rotoinversion=False)
            elif det(self.m) == 0:
                self.type = "degenerate"
                self.axis, self.angle = None, None
    def __str__(self):
        #Avoid printing '-0.' instead of '0.'
        if self.axis is not None:
            if len(self.axis) == 3:
                for i, x in enumerate(self.axis):
                    if isclose(x, 0):
                        self.axis[i] = 0.
        return ("~~ Operation: "+self.op.as_xyz_string()+" ~~"+
            "\nType: "+str(self.type)+
            "\nOrder: "+str(self.order)+
            "\nAngle: "+str(self.angle)+
            "\nAxis: "+str(np.real(self.axis)) )

    def is_conjugate(self, op2):
        '''
        Returns whether or not another operation is conjugate
        (the same operation in a different reference frame)
        Rotations with the same order will not always return True. For example,
        a 5/12 and 1/12 rotation will not be considered conjugate.
        '''
        if type(op2) != OperationAnalyzer:
            opa2 = OperationAnalyzer(op2)
            if opa2.type == self.type:
                if self.type == "rotation" or self.type == "rotoinversion":
                    ratio = self.angle / opa2.angle
                    if isclose(fabs(ratio), 1., atol=1e-2):
                        return True
                elif self.type == "identity" or self.type == "inversion":
                    return True
            else:
                return False
        else:
            if op2.type == self.type:
                if self.type == "rotation" or self.type == "rotoinversion":
                    ratio = self.angle / op2.angle
                    if isclose(ratio, 1., atol=1e-2):
                        return True
                elif self.type == "identity" or self.type == "inversion":
                    return True
            else:
                return False

    def are_conjugate(op1, op2):
        '''
        Returns whether two operations are conjugate
        '''
        if type(op1) != OperationAnalyzer:
            opa1 = OperationAnalyzer(op1)
        return opa1.is_conjugate(op2)

class orientation():
    '''
    Stores orientations for molecular crystals based on vector constraints.
    Can be stored to regenerate orientations consistent with a given constraint
    vector, without re-calling orientation_in_wyckoff_position.
    args:
        matrix: a 3x3 rotation matrix to initialize with
        degrees: the number of degrees of freedom...
            0: The orientation refers to a single rotation matrix
            1: The orientation can be rotated about a single axis
            2: The orientation can be any pure rotation matrix
    '''

    def __init__(self, matrix, degrees=0, axis=None):
        if (not is_orthogonal(matrix)):
            print("Error: Supplied orientation matrix is not orthogonal")
            return
        if (degrees == 1) and (axis is None):
            print("Error: Constraint vector required for orientation")
        self.matrix = np.array(matrix)
        self.degrees = 0
        self.axis = axis

    def get_matrix(self, angle="random"):
        #Return a SymmOp object rotated by given angle.
        #If "random", rotates by a random amount
        if self.degrees == 2:
            if angle == "random":
                return aa2matrix(1,1,random=True)
            else:
                return self.matrix
        elif self.degrees == 1:
            if angle == "random":
                R = aa2matrix(self.axis, rand()*2*pi)
                return np.dot(R, self.matrix)
            else:
                R = aa2matrix(self.axis, angle)
                return np.dot(R, self.matrix)
        elif self.degrees == 0:
            return self.matrix

    def get_op(self, angle="random"):
        #Return a SymmOp object rotated by given angle.
        #If "random", rotates by a random amount
        m = self.get_matrix(angle=angle)
        return SymmOp.from_rotation_and_translation(m,[0,0,0])

    def from_constraint(v1, c1):
        #c1 is the constraint vector; v1 will be rotated onto it
        m = rotate_vector(v1, c1)
        return orientation(m, degrees=1, axis=c1)

#Test Functionality
if __name__ == "__main__":
#----------------------------------------------------
    '''
    #Check that OperationAnalyzer works
    for string in ['x,y,z','-x,y,z','x,-y,z','x,y,-z','-x,-y,z','-x,y,-z','x,-y,-z','-x,-y,-z']:
        op = SymmOp.from_xyz_string(string)
        opa = OperationAnalyzer(op)
        print(opa)'''

    '''#Check that is_conjugate works
    from structure import random_vector
    for i in range(20):
        a = rand()*2*pi
        op2 = aa2matrix(random_vector(), a)
        print(OperationAnalyzer.are_conjugate(op1, op2))'''
    
    op = SymmOp.from_rotation_and_translation(aa2matrix([1,0,0], pi/6),[0,0,0])
    ops = [op]
    from pymatgen.symmetry.analyzer import generate_full_symmops
    symm_m = generate_full_symmops(ops, 1e-3)
    for op in symm_m:
        opa = OperationAnalyzer(op)
        print(opa.order)
