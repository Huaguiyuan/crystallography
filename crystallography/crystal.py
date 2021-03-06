"""
Module for generation of random atomic crystals with symmetry constraints. A pymatgen- or spglib-type structure object is created, which can be saved to a .cif file. Options (preceded by two dashes) are provided for command-line usage of the module:  

    spacegroup (-s): the international spacegroup number to be generated. Defaults to 206  

    element (-e): the chemical symbol of the atom(s) to use. For multiple molecule types, separate entries with commas. Ex: "C", "H, O, N". Defaults to Li  

    numIons (-n): the number of atoms in the PRIMITIVE unit cell (For P-type spacegroups, this is the same as the number of molecules in the conventional unit cell. For A, B, C, and I-centered spacegroups, this is half the number of the conventional cell. For F-centered unit cells, this is one fourth the number of the conventional cell.). For multiple atom types, separate entries with commas. Ex: "8", "1, 4, 12". Defaults to 16  

    factor (-f): the relative volume factor used to generate the unit cell. Larger values result in larger cells, with atoms spaced further apart. If generation fails after max attempts, consider increasing this value. Defaults to 2.0  

    verbosity (-v): the amount of information which should be printed for each generated structure. For 0, only prints the requested and generated spacegroups. For 1, also prints the contents of the generated pymatgen structure. Defaults to 0  

    attempts (-a): the number of structures to generate. Note: if any of the attempts fail, the number of generated structures will be less than this value. Structures will be output to separate cif files. Defaults to 10  

    outdir (-o): the file directory where cif files will be output to. Defaults to "."  
"""

import sys
#from pkg_resources import resource_string
from pkg_resources import resource_filename
from spglib import get_symmetry_dataset
from pymatgen.symmetry.groups import sg_symbol_from_int_number
from pymatgen.symmetry.analyzer import generate_full_symmops
from pymatgen.core.operations import SymmOp
from pymatgen.core.structure import Structure
from pymatgen.io.cif import CifWriter

from optparse import OptionParser
from scipy.spatial.distance import cdist
import numpy as np
from random import uniform as rand
from random import choice as choose
from random import randint
from math import sqrt, pi, sin, cos, acos, fabs
from copy import deepcopy
from pandas import read_csv

from crystallography.database.element import Element
import crystallography.database.hall as hall
from crystallography.database.layergroup import Layergroup
from crystallography.operations import OperationAnalyzer
from crystallography.operations import angle
from crystallography.operations import random_vector
from crystallography.operations import are_equal
from crystallography.operations import random_shear_matrix


#some optional libs
#from vasp import read_vasp
#from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
#from os.path import isfile

#Define variables
#------------------------------
tol_m = 1.0 #seperation tolerance in Angstroms
max1 = 30 #Attempts for generating lattices
max2 = 30 #Attempts for a given lattice
max3 = 30 #Attempts for a given Wyckoff position
minvec = 2.0 #minimum vector length
ang_min = 30
ang_max = 150
Euclidean_lattice = np.array([[1,0,0],[0,1,0],[0,0,1]])

wyckoff_df = read_csv(resource_filename("crystallography", "database/wyckoff_list.csv"))
wyckoff_symmetry_df = read_csv(resource_filename("crystallography", "database/wyckoff_symmetry.csv"))
wyckoff_generators_df = read_csv(resource_filename("crystallography", "database/wyckoff_generators.csv"))

#Define functions
#------------------------------

def gaussian(min, max, sigma=3.0):
    """
    Choose a random number from a Gaussian probability distribution centered
    between min and max. sigma is the number of standard deviations that min
    and max are away from the center. Thus, sigma is also the largest possible
    number of standard deviations corresponding to the returned value. sigma=2
    corresponds to a 95.45% probability of choosing a number between min and max

    Args:
        min: the minimum acceptable value
        max: the maximum acceptable value
        sigma: the number of standard deviations between the center and min or max

    Returns:
        a value chosen randomly between min and max
    """
    center = (max+min)*0.5
    delta = fabs(max-min)*0.5
    ratio = delta/sigma
    while True:
        x = np.random.normal(scale=ratio, loc=center)
        if x > min and x < max:
            return x
            
def letter_from_index(index, sg):
    """
    Given a Wyckoff position's index within a spacegroup,
    return its number and letter e.g. '4a'

    Args:
        index: a single integer describing the WP's index within the spacegroup (0 is the general position)
        sg: the international spacegroup number
   
    Returns:
        the Wyckoff letter corresponding to the Wyckoff position (for example, for position 4a, the function would return 'a')
    """
    letters = "abcdefghijklmnopqrstuvwxyzA"
    wyckoffs = get_wyckoffs(sg)
    length = len(wyckoffs)
    return letters[length - 1 - index]

def index_from_letter(letter, sg):
    """
    Given the Wyckoff letter, returns the index of a Wyckoff position within the spacegroup

    Args:
        letter: The wyckoff letter
        sg: the internationl spacegroup number

    Returns:
        a single index specifying the location of the Wyckoff position within the spacegroup (0 is the general position)
    """
    letters = "abcdefghijklmnopqrstuvwxyzA"
    wyckoffs = get_wyckoffs(sg)
    length = len(wyckoffs)
    return length - 1 - letters.index(letter)

def jk_from_i(i, olist):
    """
    Given an organized list (Wyckoff positions or orientations), determine
    the two indices which correspond to a single index for an unorganized list. Used mainly for organized Wyckoff position lists, but can be used for other lists organized in a similar way

    Args:
        i: a single index corresponding to the item's location in the unorganized list
        olist: the organized list

    Returns:
        [j, k]: two indices corresponding to the item's location in the organized list
    """
    num = -1
    found = False
    for j , a in enumerate(olist):
        for k , b in enumerate(a):
            num += 1
            if num == i:
                return [j, k]
    print("Error: Incorrect Wyckoff position list or index passed to jk_from_i")
    return None

def i_from_jk(j, k, olist):
    num = -1
    for x, a in enumerate(olist):
        for y, b in enumerate(a):
            num += 1
            if x == j and y == k:
                return num

def ss_string_from_ops(ops, sg, complete=True):
    """
    Print the Hermann-Mauguin symbol for a site symmetry group, using a list of
    SymmOps as input. Note that the symbol does not necessarily refer to the
    x,y,z axes. For information on reading these symbols, see:
    http://en.wikipedia.org/wiki/Hermann-Mauguin_notation#Point_groups

    Args:
        ops: a list of SymmOp objects representing the site symmetry
        sg: International number of the spacegroup. Used to determine which
            axes to show. For example, a 3-fold rotation in a cubic system is
            written as ".3.", whereas a 3-fold rotation in a trigonal system
            is written as "3.."
        complete: whether or not all symmetry operations in the group
            are present. If False, we generate the rest

    Returns:
        a string representing the site symmetry. Ex: "2mm"
    """
    #Return the symbol for a single axis
    #Will be called later in the function
    def get_symbol(opas, order, has_reflection):
        #ops: a list of Symmetry operations about the axis
        #order: highest order of any symmetry operation about the axis
        #has_reflection: whether or not the axis has mirror symmetry
        if has_reflection is True:
            #rotations have priority
            for opa in opas:
                if opa.order == order and opa.type == "rotation":
                    return str(opa.rotation_order)+"/m"
            for opa in opas:
                if (opa.order == order and opa.type == "rotoinversion"
                    and opa.order != 2):
                    return "-"+str(opa.rotation_order)
            return "m"
        elif has_reflection is False:
            #rotoinversion has priority
            for opa in opas:
                if opa.order == order and opa.type == "rotoinversion":
                    return "-"+str(opa.rotation_order)
            for opa in opas:
                if opa.order == order and opa.type == "rotation":
                    return str(opa.rotation_order)
            return "."
    #Given a list of single-axis symbols, return the one with highest symmetry
    #Will be called later in the function
    def get_highest_symbol(symbols):
        symbol_list = ['.','2','m','-2','2/m','3','4','-4','4/m','-3','6','-6','6/m']
        max_index = 0
        for symbol in symbols:
            i = symbol_list.index(symbol)
            if i > max_index:
                max_index = i
        return symbol_list[max_index]
    #Return whether or not two axes are symmetrically equivalent
    #It is assumed that both axes possess the same symbol
    #Will be called within combine_axes
    def are_symmetrically_equivalent(index1, index2):
        axis1 = axes[index1]
        axis2 = axes[index2]
        condition1 = False
        condition2 = False
        #Check for an operation mapping one axis onto the other
        for op in ops:
            if condition1 is False or condition2 is False:
                new1 = op.operate(axis1)
                new2 = op.operate(axis2)
                if np.isclose(abs(np.dot(new1, axis2)), 1):
                    condition1 = True
                if np.isclose(abs(np.dot(new2, axis1)), 1):
                    condition2 = True
        if condition1 is True and condition2 is True:
            return True
        else:
            return False
    #Given a list of axis indices, return the combined symbol
    #Axes may or may not be symmetrically equivalent, but must be of the same
    #type (x/y/z, face-diagonal, body-diagonal)
    #Will be called for mid- and high-symmetry crystallographic point groups
    def combine_axes(indices):
        symbols = {}
        for index in deepcopy(indices):
            symbol = get_symbol(params[index],orders[index],reflections[index])
            if symbol == ".":
                indices.remove(index)
            else:
                symbols[index] = symbol
        if indices == []:
            return "."
        #Remove redundant axes
        for i in deepcopy(indices):
            for j in deepcopy(indices):
                if j > i:
                    if symbols[i] == symbols[j]:
                        if are_symmetrically_equivalent(i, j):
                            if j in indices:
                                indices.remove(j)
        #Combine symbols for non-equivalent axes
        new_symbols = []
        for i in indices:
            new_symbols.append(symbols[i])
        symbol = ""
        while new_symbols != []:
            highest = get_highest_symbol(new_symbols)
            symbol += highest
            new_symbols.remove(highest)
        if symbol == "":
            print("Error: could not combine site symmetry axes.")
            return
        else:
            return symbol
    #Generate needed ops
    if complete is False:
        ops = generate_full_symmops(ops, 1e-3)
    #Get OperationAnalyzer object for all ops
    opas = []
    for op in ops:
        opas.append(OperationAnalyzer(op))
    #Store the symmetry of each axis
    params = [[],[],[],[],[],[],[],[],[],[],[],[],[]]
    has_inversion = False
    #Store possible symmetry axes for crystallographic point groups
    axes = [[1,0,0],[0,1,0],[0,0,1],
            [1,1,0],[0,1,1],[1,0,1],[1,-1,0],[0,1,-1],[1,0,-1],
            [1,1,1],[-1,1,1],[1,-1,1],[1,1,-1]]
    for i, axis in enumerate(axes):
        axes[i] = axis/np.linalg.norm(axis)
    for opa in opas:
        if opa.type != "identity" and opa.type != "inversion":
            found = False
            for i, axis in enumerate(axes):
                if np.isclose(abs(np.dot(opa.axis, axis)), 1):
                    found = True
                    params[i].append(opa)
            #Store uncommon axes for trigonal and hexagonal lattices
            if found is False:
                axes.append(opa.axis)
                #Check that new axis is not symmetrically equivalent to others
                unique = True
                for i, axis in enumerate(axes):
                    if i != len(axes)-1:
                        if are_symmetrically_equivalent(i, len(axes)-1):
                            unique = False
                if unique is True:
                    params.append([opa])
                elif unique is False:
                    axes.pop()
        elif opa.type == "inversion":
            has_inversion = True
    #Determine how many high-symmetry axes are present
    n_axes = 0
    #Store the order of each axis
    orders = []
    #Store whether or not each axis has reflection symmetry
    reflections = []
    for axis in params:
        order = 1
        high_symm = False
        has_reflection = False
        for opa in axis:
            if opa.order >= 3:
                high_symm = True
            if opa.order > order:
                order = opa.order
            if opa.order == 2 and opa.type == "rotoinversion":
                has_reflection = True
        orders.append(order)
        if high_symm == True:
            n_axes += 1
        reflections.append(has_reflection)
    #Triclinic, monoclinic, orthorhombic
    #Positions in symbol refer to x,y,z axes respectively
    if sg >= 1 and sg <= 74:
        symbol = (get_symbol(params[0], orders[0], reflections[0])+
                get_symbol(params[1], orders[1], reflections[1])+
                get_symbol(params[2], orders[2], reflections[2]))
        if symbol != "...":
            return symbol
        elif symbol == "...":
            if has_inversion is True:
                return "-1"
            else:
                return "1"
    #Trigonal, Hexagonal, Tetragonal
    elif sg >= 75 and sg <= 194:
        #1st symbol: z axis
        s1 = get_symbol(params[2], orders[2], reflections[2])
        #2nd symbol: x or y axes (whichever have higher symmetry)
        s2 = combine_axes([0,1])
        #3rd symbol: face-diagonal axes (whichever have highest symmetry)
        s3 = combine_axes(list(range(3, len(axes))))
        symbol = s1+" "+s2+" "+s3
        if symbol != ". . .":
            return symbol
        elif symbol == ". . .":
            if has_inversion is True:
                return "-1"
            else:
                return "1"
    #Cubic
    elif sg >= 195 and sg <= 230:
        pass
        #1st symbol: x, y, and/or z axes (whichever have highest symmetry)
        s1 = combine_axes([0,1,2])
        #2nd symbol: body-diagonal axes (whichever has highest symmetry)
        s2 = combine_axes([9,10,11,12])
        #3rd symbol: face-diagonal axes (whichever have highest symmetry)
        s3 = combine_axes([3,4,5,6,7,8])
        symbol = s1+" "+s2+" "+s3
        if symbol != ". . .":
            return symbol
        elif symbol == ". . .":
            if has_inversion is True:
                return "-1"
            else:
                return "1"
    else:
        print("Error: invalid spacegroup number")
        return

def create_matrix(PBC=None):
    """
    Used for calculating distances in lattices with periodic boundary conditions. When multiplied with a set of points, generates additional points in cells adjacent to and diagonal to the original cell

    Args:
        PBC: an axis which does not have periodic boundary condition. Ex: PBC=1 cancels periodic boundary conditions along the x axis

    Returns:
        A numpy array of matrices which can be multiplied by a set of coordinates
    """
    matrix = []
    i_list = [-1, 0, 1]
    j_list = [-1, 0, 1]
    k_list = [-1, 0, 1]
    if PBC == 1:
        i_list = [0]
    elif PBC == 2:
        j_list = [0]
    elif PBC == 3:
        k_list = [0]
    for i in i_list:
        for j in j_list:
            for k in k_list:
                matrix.append([i,j,k])
    return np.array(matrix, dtype=float)

#Euclidean distance
def distance(xyz, lattice, PBC=None): 
    xyz = xyz - np.round(xyz)
    matrix = create_matrix(PBC)
    matrix += xyz
    matrix = np.dot(matrix, lattice)
    return np.min(cdist(matrix,[[0,0,0]]))       

def check_distance(coord1, coord2, specie1, specie2, lattice, PBC=None, d_factor=1.0):
    """
    Check the distances between two set of molecules. The first set is generally
    larger than the second. Distances between coordinates within the first set are
    not checked, and distances between coordinates within the second set are not
    checked. Only distances between points from different sets are checked.

    Args:
        coord1: multiple lists of fractional coordinates e.g. [[[.1,.6,.4],[.3,.8,.2]],[[.4,.4,.4],[.3,.3,.3]]]
        coord2: a list of new fractional coordinates e.g. [[.7,.8,.9], [.4,.5,.6]]
        specie1: a list of atomic symbols for coord1. Ex: ['C', 'O']
        specie2: the atomic symbol for coord2. Ex: 'Li'
        lattice: matrix describing the unit cell vectors
        PBC: value to be passed to create_matrix
        d_factor: the tolerance is multiplied by this amount. Larger values mean atoms must be farther apart

    Returns:
        a bool for whether or not the atoms are sufficiently far enough apart
    """
    #add PBC
    coord2s = []
    matrix = create_matrix(PBC)
    for coord in coord2:
        for m in matrix:
            coord2s.append(coord+m)
    coord2 = np.array(coord2s)

    coord2 = np.dot(coord2, lattice)
    if len(coord1)>0:
        for coord, element in zip(coord1, specie1):
            coord = np.dot(coord, lattice)
            d_min = np.min(cdist(coord, coord2))
            tol = d_factor*0.5*(Element(element).covalent_radius + Element(specie2).covalent_radius)
            #print(d_min, tol)
            if d_min < tol:
                return False
        return True
    else:
        return True

def get_center(xyzs, lattice, PBC=None):
    """
    Finds the geometric centers of the clusters under periodic boundary conditions.

    Args:
        xyzs: a list of fractional coordinates
        lattice: a matrix describing the unit cell
        PBC: a value to be passed to create_matrix

    Returns:
        x,y,z coordinates for the center of the input coordinate list
    """
    matrix0 = create_matrix(PBC)
    xyzs -= np.round(xyzs)
    for atom1 in range(1,len(xyzs)):
        dist_min = 10.0
        for atom2 in range(0, atom1):
            #shift atom1 to position close to atom2
            matrix = matrix0 + (xyzs[atom1] - xyzs[atom2])
            matrix = np.dot(matrix, lattice)
            dists = cdist(matrix, [[0,0,0]])
            if np.min(dists) < dist_min:
                dist_min = np.min(dists)
                matrix_min = matrix0[np.argmin(dists)]
        xyzs[atom1] += matrix_min
    center = xyzs.mean(0)
    if abs(center[PBC-1])<1e-4:
        center[PBC-1] = 0.5
    return center

def para2matrix(cell_para, radians=True, format='lower'):
    """
    Given a set of lattic parameters, generates a matrix representing the lattice vectors

    Args:
        cell_para: a 1x6 list of lattice parameters [a, b, c, alpha, beta, gamma]. a, b, and c are the length of the lattice vectos, and alpha, beta, and gamma are the angles between these vectors. Can be generated by matrix2para
        radians: if True, lattice parameters should be in radians. If False, lattice angles should be in degrees
        format: a string ('lower', 'symmetric', or 'upper') for the type of matrix to be output

    Returns:
        a 3x3 matrix representing the unit cell. By default (format='lower'), the a vector is aligined along the x-axis, and the b vector is in the y-z plane
    """
    a = cell_para[0]
    b = cell_para[1]
    c = cell_para[2]
    alpha = cell_para[3]
    beta = cell_para[4]
    gamma = cell_para[5]
    if radians is not True:
        rad = pi/180.
        alpha *= rad
        beta *= rad
        gamma *= rad
    cos_alpha = np.cos(alpha)
    cos_beta = np.cos(beta)
    cos_gamma = np.cos(gamma)
    sin_gamma = np.sin(gamma)
    sin_alpha = np.sin(alpha)
    matrix = np.zeros([3,3])
    if format == 'lower':
        #Generate a lower-diagonal matrix
        c1 = c*cos_beta
        c2 = (c*(cos_alpha - (cos_beta * cos_gamma))) / sin_gamma
        matrix[0][0] = a
        matrix[1][0] = b * cos_gamma
        matrix[1][1] = b * sin_gamma
        matrix[2][0] = c1
        matrix[2][1] = c2
        matrix[2][2] = sqrt(c**2 - c1**2 - c2**2)
    elif format == 'symmetric':
        #TODO: allow generation of symmetric matrices
        pass
    elif format == 'upper':
        #Generate an upper-diagonal matrix
        a3 = a*cos_beta
        a2 = (a*(cos_gamma - (cos_beta * cos_alpha))) / sin_alpha
        matrix[2][2] = c
        matrix[1][2] = b * cos_alpha
        matrix[1][1] = b * sin_alpha
        matrix[0][2] = a3
        matrix[0][1] = a2
        matrix[0][0] = sqrt(a**2 - a3**2 - a2**2)
        pass
    return matrix

def Add_vacuum(lattice, coor, vacuum=10.0, dim = 2):
    '''
    TODO: Add documentation
    '''
    old = lattice[dim, dim]
    new = old + vacuum
    coor[:,dim] = coor[:,dim]*old/new
    coor[:,dim] = coor[:,dim] - np.mean(coor[:,dim]) + 0.5
    lattice[dim, dim] = new
    return lattice, coor

def Permutation(lattice, coor, PB):
    """
    TODO: Add documentation
    """
    para = matrix2para(lattice)
    para1 = deepcopy(para)
    coor1 = deepcopy(coor)
    for axis in [0,1,2]:
        para1[axis] = para[PB[axis]-1]
        para1[axis+3] = para[PB[axis]+2]
        coor1[:,axis] = coor[:,PB[axis]-1]
    #print('before permutation: ', para)
    #print('after permutation: ', para1)
    return para2matrix(para1), coor1

def matrix2para(matrix, radians=True):
    """
    """
    cell_para = np.zeros(6)
    #a
    cell_para[0] = np.linalg.norm(matrix[0])
    #b
    cell_para[1] = np.linalg.norm(matrix[1])
    #c
    cell_para[2] = np.linalg.norm(matrix[2])
    #alpha
    cell_para[3] = angle(matrix[1], matrix[2])
    #beta
    cell_para[4] = angle(matrix[0], matrix[2])
    #gamma
    cell_para[5] = angle(matrix[0], matrix[1])
    
    if not radians:
        #convert radians to degrees
        deg = 180./pi
        cell_para[3] *= deg
        cell_para[4] *= deg
        cell_para[5] *= deg
    return cell_para

def cellsize(sg):
    """
    Returns the number of duplications in the conventional lattice
    """
    symbol = sg_symbol_from_int_number(sg)
    letter = symbol[0]
    if letter == 'P':
    	return 1
    if letter in ['A', 'C', 'I']:
    	return 2
    elif letter in ['R']:
    	return 3
    elif letter in ['F']:
    	return 4
    else: return "Error: Could not determine lattice type"

def find_short_dist(coor, lattice, tol):
    """
    here we find the atomic pairs with shortest distance
    and then build the connectivity map
    """
    pairs=[]
    graph=[]
    for i in range(len(coor)):
        graph.append([])

    for i1 in range(len(coor)-1):
        for i2 in range(i1+1,len(coor)):
            dist = distance(coor[i1]-coor[i2], lattice)
            if dist <= tol:
                #dists.append(dist)
                pairs.append([i1,i2,dist])
    pairs = np.array(pairs)
    if len(pairs) > 0:
        #print('--------', dists <= (min(dists) + 0.1))
        d_min = min(pairs[:,-1]) + 1e-3
        sequence = [pairs[:,-1] <= d_min]
        #print(sequence)
        pairs = pairs[sequence]
        #print(pairs)
        #print(len(coor))
        for pair in pairs:
            pair0=int(pair[0])
            pair1=int(pair[1])
            #print(pair0, pair1, len(graph))
            graph[pair0].append(pair1)
            graph[pair1].append(pair0)

    return pairs, graph

def connected_components(graph):
    """
    Given an undirected graph (a 2d array of indices), return a set of
    connected components, each connected component being an (arbitrarily
    ordered) array of indices which are connected either directly or indirectly.
    """
    def add_neighbors(el, seen=[]):
        '''
        Find all elements which are connected to el. Return an array which
        includes these elements and el itself.
        '''
        #seen stores already-visited indices
        if seen == []: seen = [el]
        #iterate through the neighbors (x) of el
        for x in graph[el]:
            if x not in seen:
                seen.append(x)
                #Recursively find neighbors of x
                add_neighbors(x, seen)
        return seen

    #Create a list of indices to iterate through
    unseen = list(range(len(graph)))
    sets = []
    i = 0
    while (unseen != []):
        #x is the index we are finding the connected component of
        x = unseen.pop()
        sets.append([])
        #Add neighbors of x to the current connected component
        for y in add_neighbors(x):
            sets[i].append(y)
            #Remove indices which have already been found
            if y in unseen: unseen.remove(y)
        i += 1
    return sets

def merge_coordinate(coor, lattice, wyckoff, sg, tol, PBC=None):
    while True:
        pairs, graph = find_short_dist(coor, lattice, tol)
        index = None
        if len(pairs)>0:
            if len(coor) > len(wyckoff[-1][0]):
                merged = []
                groups = connected_components(graph)
                for group in groups:
                    merged.append(get_center(coor[group], lattice, PBC))
                merged = np.array(merged)
                #if check_wyckoff_position(merged, sg, wyckoff) is not False:
                index = check_wyckoff_position(merged, sg, exact_translation=False)
                if index is False:
                    return coor, False
                else:
                    coor = merged

            else:#no way to merge
                #print('no way to Merge, FFFFFFFFFFFFFFFFFFFFFFF----------------')
                return coor, False
        else:
            if index is None:
                index = check_wyckoff_position(coor, sg, exact_translation=False)
            return coor, index

def estimate_volume(numIons, species, factor=2.0):
    volume = 0
    for numIon, specie in zip(numIons, species):
        volume += numIon*4/3*pi*Element(specie).covalent_radius**3
    return factor*volume

def generate_lattice(sg, volume, minvec=tol_m, minangle=pi/6, max_ratio=10.0, maxattempts = 100):
    """
    generate the lattice according to the space group symmetry and number of atoms
    if the space group has centering, we will transform to conventional cell setting
    If the generated lattice does not meet the minimum angle and vector requirements,
    we try to generate a new one, up to maxattempts times

    args:
        sg: International number of the space group
        volume: volume of the lattice
        minvec: minimum allowed lattice vector length (among a, b, and c)
        minangle: minimum allowed lattice angle (among alpha, beta, and gamma)
        max_ratio: largest allowed ratio of two lattice vector lengths
    """
    maxangle = pi-minangle
    for n in range(maxattempts):
        #Triclinic
        if sg <= 2:
            #Derive lattice constants from a random matrix
            mat = random_shear_matrix(width=0.2)
            a, b, c, alpha, beta, gamma = matrix2para(mat)
            x = sqrt(1-cos(alpha)**2 - cos(beta)**2 - cos(gamma)**2 + 2*(cos(alpha)*cos(beta)*cos(gamma)))
            vec = random_vector()
            abc = volume/x
            xyz = vec[0]*vec[1]*vec[2]
            a = vec[0]*np.cbrt(abc)/np.cbrt(xyz)
            b = vec[1]*np.cbrt(abc)/np.cbrt(xyz)
            c = vec[2]*np.cbrt(abc)/np.cbrt(xyz)
        #Monoclinic
        elif sg <= 15:
            alpha, gamma  = pi/2, pi/2
            beta = gaussian(minangle, maxangle)
            x = sin(beta)
            vec = random_vector()
            xyz = vec[0]*vec[1]*vec[2]
            abc = volume/x
            a = vec[0]*np.cbrt(abc)/np.cbrt(xyz)
            b = vec[1]*np.cbrt(abc)/np.cbrt(xyz)
            c = vec[2]*np.cbrt(abc)/np.cbrt(xyz)
        #Orthorhombic
        elif sg <= 74:
            alpha, beta, gamma = pi/2, pi/2, pi/2
            x = 1
            vec = random_vector()
            xyz = vec[0]*vec[1]*vec[2]
            abc = volume/x
            a = vec[0]*np.cbrt(abc)/np.cbrt(xyz)
            b = vec[1]*np.cbrt(abc)/np.cbrt(xyz)
            c = vec[2]*np.cbrt(abc)/np.cbrt(xyz)
        #Tetragonal
        elif sg <= 142:
            alpha, beta, gamma = pi/2, pi/2, pi/2
            x = 1
            vec = random_vector()
            c = vec[2]/(vec[0]*vec[1])*np.cbrt(volume/x)
            a = b = sqrt((volume/x)/c)
        #Trigonal/Rhombohedral/Hexagonal
        elif sg <= 194:
            alpha, beta, gamma = pi/2, pi/2, pi/3*2
            x = sqrt(3.)/2.
            vec = random_vector()
            c = vec[2]/(vec[0]*vec[1])*np.cbrt(volume/x)
            a = b = sqrt((volume/x)/c)
        #Cubic
        else:
            alpha, beta, gamma = pi/2, pi/2, pi/2
            s = (volume) ** (1./3.)
            a, b, c = s, s, s
        #Check that lattice meets requirements
        maxvec = (a*b*c)/(minvec**2)
        if minvec < maxvec:
            #Check minimum Euclidean distances
            smallvec = min(a*cos(max(beta, gamma)), b*cos(max(alpha, gamma)), c*cos(max(alpha, beta)))
            if(a>minvec and b>minvec and c>minvec
            and a<maxvec and b<maxvec and c<maxvec
            and smallvec < minvec
            and alpha>minangle and beta>minangle and gamma>minangle
            and alpha<maxangle and beta<maxangle and gamma<maxangle
            and a/b<max_ratio and a/c<max_ratio and b/c<max_ratio
            and b/a<max_ratio and c/a<max_ratio and c/b<max_ratio):
                return np.array([a, b, c, alpha, beta, gamma])
            #else:
                #print([a, b, c, maxvec, minvec, maxvec*minvec*minvec])
    #If maxattempts tries have been made without success
    print("Error: Could not generate lattice after "+str(n+1)+" attempts for volume ", volume)
    return

def generate_lattice_2d(sg, volume, thickness, P, minvec=tol_m, minangle=pi/6, max_ratio=10.0, maxattempts = 100):
    """
    generate the lattice according to the space group symmetry and number of atoms
    if the space group has centering, we will transform to conventional cell setting
    If the generated lattice does not meet the minimum angle and vector requirements,
    we try to generate a new one, up to maxattempts times

    args:
        sg: International number of the space group
        volume: volume of the lattice
        minvec: minimum allowed lattice vector length (among a, b, and c)
        minangle: minimum allowed lattice angle (among alpha, beta, and gamma)
        max_ratio: largest allowed ratio of two lattice vector lengths
    """
    maxangle = pi-minangle
    abc = np.ones([3])
    abc[2] = thickness
    alpha, beta, gamma  = pi/2, pi/2, pi/2
    for n in range(maxattempts):
        #Triclinic
        if sg <= 2:
            vec = random_vector()

        #Monoclinic
        elif sg <= 15:
            if P[-1]==3 and sg_symbol_from_int_number(sg)=='P':
                gamma = gaussian(minangle, maxangle)
            x = sin(beta)
            vec = random_vector()
            ratio = sqrt(volume/x*vec[2]/abc[2])
            abc[0]=vec[0]*ratio
            abc[1]=vec[1]*ratio

        #Orthorhombic
        elif sg <= 74:
            vec = random_vector()
            ratio = sqrt(volume*vec[2]/abc[2])
            abc[0]=vec[0]*ratio
            abc[1]=vec[1]*ratio

        #Tetragonal
        elif sg <= 142:
            abc[0] = abc[1] = sqrt(volume/abc[2])

        #Trigonal/Rhombohedral/Hexagonal
        elif sg <= 194:
            gamma = pi/3*2
            x = sqrt(3.)/2.
            abc[0] = abc[1] = sqrt((volume/x)/abc[2])

        para = np.array([abc[0], abc[1], abc[2], alpha, beta, gamma])
        para1 = deepcopy(para)
        for axis in [0,1,2]:
            para1[axis] = para[P[axis]-1]
            para1[axis+3] = para[P[axis]+2]
        #print('before: ', para)
        #print('after : ', para1)
        return para1

    #If maxattempts tries have been made without success
    print("Error: Could not generate lattice after "+str(n+1)+" attempts")
    return

def choose_wyckoff(wyckoffs, number):
    """
    choose the wyckoff sites based on the current number of atoms
    rules 
    1, the newly added sites is equal/less than the required number.
    2, prefer the sites with large multiplicity
    """
    if rand(0,1)>0.5: #choose from high to low
        for wyckoff in wyckoffs:
            if len(wyckoff[0]) <= number:
                return choose(wyckoff)
        return False
    else:
        good_wyckoff = []
        for wyckoff in wyckoffs:
            if len(wyckoff[0]) <= number:
                for w in wyckoff:
                    good_wyckoff.append(w)
        if len(good_wyckoff) > 0:
            return choose(good_wyckoff)
        else:
            return False

def get_wyckoffs(sg, organized=False, PB=None):
    """
    Returns a list of Wyckoff positions for a given space group.
    1st index: index of WP in sg (0 is the WP with largest multiplicity)
    2nd index: a SymmOp object in the WP
    """
    if PB is not None:
        coor = [0,0,0]
        #coor[0] = 0.5
        #print(coor[0], coor[1], coor[2])
        coor[PB[-1]-1] = 0.5
        coor = np.array(coor)

    wyckoff_strings = eval(wyckoff_df["0"][sg])
    wyckoffs = []
    for x in wyckoff_strings:
        if PB is not None:
            op = SymmOp.from_xyz_string(x[0])
            coor1 = op.operate(coor)
            if abs(coor1[PB[-1]-1]-0.5) < 1e-2:
                #print('invalid wyckoffs for layer group: ', x[0], coor, coor1)
                wyckoffs.append([])
                for y in x:
                    wyckoffs[-1].append(SymmOp.from_xyz_string(y))
        else:
            wyckoffs.append([])
            for y in x:
                wyckoffs[-1].append(SymmOp.from_xyz_string(y))
    if organized:
        wyckoffs_organized = [[]] #2D Array of WP's organized by multiplicity
        old = len(wyckoffs[0])
        for wp in wyckoffs:
            mult = len(wp)
            if mult != old:
                wyckoffs_organized.append([])
                old = mult
            wyckoffs_organized[-1].append(wp)
        return wyckoffs_organized
    else:
        return wyckoffs

def get_wyckoff_symmetry(sg, molecular=False):
    """
    Returns a list of Wyckoff position site symmetry for a given space group.
    1st index: index of WP in sg (0 is the WP with largest multiplicity)
    2nd index: a point within the WP
    3rd index: a site symmetry SymmOp of the point
    molecular: whether or not to return the Euclidean point symmetry operations
        If True, cuts off translational part of operation, and converts non-orthogonal
        (3-fold and 6-fold rotation) operations to pure rotations
    """
    P = SymmOp.from_rotation_and_translation([[1,-.5,0],[0,sqrt(3)/2,0],[0,0,1]], [0,0,0])
    symmetry_strings = eval(wyckoff_symmetry_df["0"][sg])
    symmetry = []
    convert = False
    if molecular is True:
        if sg >= 143 and sg <= 194:
            convert = True
    #Loop over Wyckoff positions
    for x in symmetry_strings:
        symmetry.append([])
        #Loop over points in WP
        for y in x:
            symmetry[-1].append([])
            #Loop over ops
            for z in y:
                op = SymmOp.from_xyz_string(z)
                if convert is True:
                    #Convert non-orthogonal trigonal/hexagonal operations
                    op = P*op*P.inverse
                if molecular is False:
                    symmetry[-1][-1].append(op)
                elif molecular is True:
                    op = SymmOp.from_rotation_and_translation(op.rotation_matrix,[0,0,0])
                    symmetry[-1][-1].append(op)
    return symmetry

def get_wyckoff_generators(sg):
    """
    Returns a list of Wyckoff generators for a given space group.
    1st index: index of WP in sg (0 is the WP with largest multiplicity)
    2nd index: a generator for the WP
    """
    generators_strings = eval(wyckoff_generators_df["0"][sg])
    generators = []
    #Loop over Wyckoff positions
    for wp in generators_strings:
        generators.append([])
        #Loop over points in WP
        for op in wp:
            generators[-1].append(SymmOp.from_xyz_string(op))
    return generators

def site_symm(point, gen_pos, tol=1e-3, lattice=Euclidean_lattice):
    """
    Given gen_pos (a list of SymmOps), return the list of symmetry operations
    leaving a point (coordinate or SymmOp) invariant.
    """
    #Convert point into a SymmOp
    if type(point) != SymmOp:
        point = SymmOp.from_rotation_and_translation([[0,0,0],[0,0,0],[0,0,0]], point)
    symmetry = []
    for op in gen_pos:
        is_symmetry = True
        #Calculate the effect of applying op to point
        difference = SymmOp((op*point).affine_matrix - point.affine_matrix)
        #Check that the rotation matrix is unaltered by op
        if not np.allclose(difference.rotation_matrix, np.zeros((3,3)), rtol = 1e-3, atol = 1e-3):
            is_symmetry = False
        #Check that the displacement is less than tol
        displacement = difference.translation_vector
        if distance(displacement, lattice) > tol:
            is_symmetry = False
        if is_symmetry:
            '''The actual site symmetry's translation vector may vary from op by
            a factor of +1 or -1 (especially when op contains +-1/2).
            We record this to distinguish between special Wyckoff positions.
            As an example, consider the point (-x+1/2,-x,x+1/2) in position 16c
            of space group Ia-3(206). The site symmetry includes the operations
            (-z+1,x-1/2,-y+1/2) and (y+1/2,-z+1/2,-x+1). These operations are
            not listed in the general position, but correspond to the operations
            (-z,x+1/2,-y+1/2) and (y+1/2,-z+1/2,-x), respectively, just shifted
            by (+1,-1,0) and (0,0,+1), respectively.
            '''
            el = SymmOp.from_rotation_and_translation(op.rotation_matrix, op.translation_vector - np.round(displacement))
            symmetry.append(el)
    return symmetry

def find_generating_point(coords, generators):
    #Given a set of coordinates and Wyckoff generators, return the coord which
    #can be used to generate the others
    for coord in coords:
        generated = list(gen.operate(coord) for gen in generators)
        generated -= np.floor(generated)
        tmp_c = deepcopy(coords)
        tmp_c -= np.floor(tmp_c)
        index_list1 = list(range(len(tmp_c)))
        index_list2 = list(range(len(generated)))
        if len(generated) != len(tmp_c):
            print("Warning: coordinate and generator lists have unequal length.")
            print("In check_wyckoff_position_molecular.find_generating_point:")
            print("len(coords): "+str(len(coords))+", len(generators): "+str(len(generators)))
            return None
        for index1, c1 in enumerate(tmp_c):
            for index2, c2 in enumerate(generated):
                if np.allclose(c1, c2, atol=.001, rtol=.001):
                    if index1 in index_list1:
                        index_list1.remove(index1)
                    if index2 in index_list2:
                        index_list2.remove(index2)
                    break
        if index_list1 == [] and index_list2 == []:
            return coord
    #If no valid coordinate is found
    return None

def check_wyckoff_position(points, sg, wyckoffs=None, exact_translation=False):
    """
    Given a list of points, return index of Wyckoff position in space group.
    If no match found, returns False.

    Args:
        points: a list of 3d coordinates or SymmOps to check
        sg: the international space group number to check
        wyckoffs: a list of Wyckoff positions obtained from get_wyckoffs.
        exact_translation: whether we require two SymmOps to have exactly equal
            translational components. If false, translations related by +-1
            are considered equal
    """
    points = np.array(points)
    points = np.around((points*1e+10))/1e+10

    if wyckoffs == None:
        wyckoffs = get_wyckoffs(sg)
        gen_pos = wyckoffs[0]
    else:
        gen_pos = wyckoffs[0][0]
    new_points = []
    #
    if exact_translation == False:
        for p in points:
            new_points.append(p - np.floor(p))
        points = new_points
    w_symm_all = get_wyckoff_symmetry(sg)
    p_symm = []
    #If exact_translation is false, store WP's which might be a match
    possible = []
    for x in points:
        p_symm.append(site_symm(x, gen_pos))
    for i, wp in enumerate(wyckoffs):
        w_symm = w_symm_all[i]
        if len(p_symm) == len(w_symm):
            temp = deepcopy(w_symm)
            for p in p_symm:
                for w in temp:
                    if exact_translation:
                        if p == w:
                            temp.remove(w)
                    elif not exact_translation:
                        temp2 = deepcopy(w)
                        for op_p in p:
                            for op_w in w:
                                #Check that SymmOp's are equal up to some integer translation
                                if are_equal(op_w, op_p, allow_pbc=True):
                                    temp2.remove(op_w)
                        if temp2 == []:
                            temp.remove(w)
            if temp == []:
                #If we find a match with exact translations
                if exact_translation:
                    return i
                elif not exact_translation:
                    possible.append(i)
        #If no matching WP's are found
    if len(possible) == 0:
        return False
    #If exactly one matching WP is found
    elif len(possible) == 1:
        return possible[0]
    #If multiple WP's are found
    else:
        #Check that points are generated from generators
        for i in possible:
            p = find_generating_point(points, generators)
            if p is not None:
                return i
        print("Error: Could not generate Wyckoff position from generators")
        return False

def verify_distances(coordinates, species, lattice, factor=1.0):
    for i, c1 in enumerate(coordinates):
        specie1 = species[i]
        for j, c2 in enumerate(coordinates):
            if j > i:
                specie2 = species[j]
                diff = np.array(c2) - np.array(c1)
                d_min = distance(diff, lattice)
                tol = factor*0.5*(Element(specie1).covalent_radius + Element(specie2).covalent_radius)
                if d_min < tol:
                    return False
    return True

class random_crystal():
    def __init__(self, sg, species, numIons, factor):
        
        #Necessary input
        numIons = np.array(numIons) #must convert it to np.array
        self.factor = factor
        self.numIons0 = numIons
        self.sg = sg
        self.species = species
        self.Msgs()
        self.numIons = numIons * cellsize(self.sg)
        self.volume = estimate_volume(self.numIons, self.species, self.factor)
        self.wyckoffs = get_wyckoffs(self.sg, organized=True) #2D Array of Wyckoff positions organized by multiplicity
        self.generate_crystal()


    def Msgs(self):
        self.Msg1 = 'Error: the number is incompatible with the wyckoff sites choice'
        self.Msg2 = 'Error: failed in the cycle of generating structures'
        self.Msg3 = 'Warning: failed in the cycle of adding species'
        self.Msg4 = 'Warning: failed in the cycle of choosing wyckoff sites'
        self.Msg5 = 'Finishing: added the specie'
        self.Msg6 = 'Finishing: added the whole structure'

    def check_compatible(self):
        """
        check if the number of atoms is compatible with the wyckoff positions
        needs to improve later
        """
        N_site = [len(x[0]) for x in self.wyckoffs]
        has_freedom = False
        #remove WP's with no freedom once they are filled
        removed_wyckoffs = []
        for numIon in self.numIons:
            #Check that the number of ions is a multiple of the smallest Wyckoff position
            if numIon % N_site[-1] > 0:
                return False
            else:
                #Check if smallest WP has at least one degree of freedom
                op = self.wyckoffs[-1][-1][0]
                if op.rotation_matrix.all() != 0.0:
                    has_freedom = True
                else:
                    #Subtract from the number of ions beginning with the smallest Wyckoff positions
                    remaining = numIon
                    for x in self.wyckoffs:
                        for wp in x:
                            removed = False
                            while remaining >= len(wp) and wp not in removed_wyckoffs:
                                #Check if WP has at least one degree of freedom
                                op = wp[0]
                                remaining -= len(wp)
                                if np.allclose(op.rotation_matrix, np.zeros([3,3])):
                                    removed_wyckoffs.append(wp)
                                    removed = True
                                else:
                                    has_freedom = True
                    if remaining != 0:
                        return False
        if has_freedom:
            return True
        else:
            #print("Warning: Wyckoff Positions have no degrees of freedom.")
            return 0

    def generate_crystal(self, max1=max1, max2=max2, max3=max3):
        """the main code to generate random crystal"""
        #Check the minimum number of degrees of freedom within the Wyckoff positions
        degrees = self.check_compatible()
        if degrees is False:
            print(self.Msg1)
            self.struct = None
            self.valid = False
            return
        else:
            if degrees is 0:
                max1 = 5
                max2 = 5
                max3 = 5
            #Calculate a minimum vector length for generating a lattice
            minvector = max(max(2.0*Element(specie).covalent_radius for specie in self.species), tol_m)
            for cycle1 in range(max1):
                #1, Generate a lattice
                cell_para = generate_lattice(self.sg, self.volume, minvec=minvector)
                if cell_para is None:
                    break
                else:
                    cell_matrix = para2matrix(cell_para)
                    if abs(self.volume - np.linalg.det(cell_matrix)) > 1.0: 
                        print('Error, volume is not equal to the estimated value: ', self.volume, ' -> ', np.linalg.det(cell_matrix))
                        print('cell_para:  ', cell_para)
                        sys.exit(0)

                    coordinates_total = [] #to store the added coordinates
                    sites_total = []      #to store the corresponding specie
                    good_structure = False

                    for cycle2 in range(max2):
                        coordinates_tmp = deepcopy(coordinates_total)
                        sites_tmp = deepcopy(sites_total)
                        
            	        #Add specie by specie
                        for numIon, specie in zip(self.numIons, self.species):
                            numIon_added = 0
                            tol = max(0.5*Element(specie).covalent_radius, tol_m)

                            #Now we start to add the specie to the wyckoff position
                            for cycle3 in range(max3):
                                #Choose a random Wyckoff position for given multiplicity: 2a, 2b, 2c
                                ops = choose_wyckoff(self.wyckoffs, numIon-numIon_added) 
                                if ops is not False:
            	        	    #Generate a list of coords from ops
                                    point = np.random.random(3)
                                    #print('generating new points:', point)
                                    coords = np.array([op.operate(point) for op in ops])
                                    #merge_coordinate if the atoms are close
                                    coords_toadd, good_merge = merge_coordinate(coords, cell_matrix, self.wyckoffs, self.sg, tol)
                                    if good_merge is not False:
                                        coords_toadd -= np.floor(coords_toadd) #scale the coordinates to [0,1], very important!
                                        #print('existing: ', coordinates_tmp)
                                        if check_distance(coordinates_tmp, coords_toadd, sites_tmp, specie, cell_matrix):
                                            coordinates_tmp.append(coords_toadd)
                                            sites_tmp.append(specie)
                                            numIon_added += len(coords_toadd)
                                        if numIon_added == numIon:
                                            coordinates_total = deepcopy(coordinates_tmp)
                                            sites_total = deepcopy(sites_tmp)
                                            break

                            if numIon_added != numIon:
                                break  #need to repeat from the 1st species

                        if numIon_added == numIon:
                            #print(self.Msg6)
                            good_structure = True
                            break
                        else: #reset the coordinates and sites
                            coordinates_total = []
                            sites_total = []

                    if good_structure:
                        final_coor = []
                        final_site = []
                        final_number = []
                        final_lattice = cell_matrix
                        for coor, ele in zip(coordinates_total, sites_total):
                            for x in coor:
                                final_coor.append(x)
                                final_site.append(ele)
                                final_number.append(Element(ele).z)

                        self.lattice = final_lattice                    
                        self.coordinates = np.array(final_coor)
                        self.sites = final_site                    
                        self.struct = Structure(final_lattice, final_site, np.array(final_coor))
                        self.spg_struct = (final_lattice, np.array(final_coor), final_number)
                        self.valid = True
                        return
        if degrees == 0: print("Wyckoff positions have no degrees of freedom.")
        self.struct = self.Msg2
        self.valid = False
        return self.Msg2

class random_crystal_2D():
    def __init__(self, number, species, numIons, thickness, factor):

        self.lgp = Layergroup(number)
        self.sg = self.lgp.sgnumber
        numIons = np.array(numIons) #must convert it to np.array
        self.factor = factor
        self.thickness = thickness
        self.numIons0 = numIons
        self.species = species
        self.PBC = self.lgp.permutation[-1] 
        self.PB = self.lgp.permutation[3:6] 
        self.P = self.lgp.permutation[:3] 
        self.Msgs()
        self.numIons = numIons * cellsize(self.sg)
        self.volume = estimate_volume(self.numIons, self.species, self.factor)
        self.wyckoffs = deepcopy(get_wyckoffs(self.sg, organized=True, PB=self.PB)) 
        self.generate_crystal()


    def Msgs(self):
        self.Msg1 = 'Error: the number is incompatible with the wyckoff sites choice'
        self.Msg2 = 'Error: failed in the cycle of generating structures'
        self.Msg3 = 'Warning: failed in the cycle of adding species'
        self.Msg4 = 'Warning: failed in the cycle of choosing wyckoff sites'
        self.Msg5 = 'Finishing: added the specie'
        self.Msg6 = 'Finishing: added the whole structure'

    def check_compatible(self):
        """
        check if the number of atoms is compatible with the wyckoff positions
        needs to improve later
        """
        N_site = [len(x[0]) for x in self.wyckoffs]
        has_freedom = False
        #remove WP's with no freedom once they are filled
        removed_wyckoffs = []
        for numIon in self.numIons:
            #Check that the number of ions is a multiple of the smallest Wyckoff position
            if numIon % N_site[-1] > 0:
                return False
            else:
                #Check if smallest WP has at least one degree of freedom
                op = self.wyckoffs[-1][-1][0]
                if op.rotation_matrix.all() != 0.0:
                    has_freedom = True
                else:
                    #Subtract from the number of ions beginning with the smallest Wyckoff positions
                    remaining = numIon
                    for x in self.wyckoffs:
                        for wp in x:
                            removed = False
                            while remaining >= len(wp) and wp not in removed_wyckoffs:
                                #Check if WP has at least one degree of freedom
                                op = wp[0]
                                remaining -= len(wp)
                                if np.allclose(op.rotation_matrix, np.zeros([3,3])):
                                    removed_wyckoffs.append(wp)
                                    removed = True
                                else:
                                    has_freedom = True
                    if remaining != 0:
                        return False
        if has_freedom:
            return True
        else:
            #print("Warning: Wyckoff Positions have no degrees of freedom.")
            return 0

    def generate_crystal(self, max1=max1, max2=max2, max3=max3):
        """the main code to generate random crystal """
        #Check the minimum number of degrees of freedom within the Wyckoff positions
        degrees = self.check_compatible()
        if degrees is 0:
            print("Generation cancelled: Wyckoff positions have no degrees of freedom.")
            self.struct = None
            self.valid = False
            return
        elif degrees is False:
            print(self.Msg1)
            self.struct = None
            self.valid = False
            return
        else:
            #Calculate a minimum vector length for generating a lattice
            minvector = max(max(2.0*Element(specie).covalent_radius for specie in self.species), tol_m)
            for cycle1 in range(max1):
                #1, Generate a lattice
                cell_para = generate_lattice_2d(self.sg, self.volume, self.thickness, self.P, minvec=minvector)
                cell_matrix = para2matrix(cell_para)
                coordinates_total = [] #to store the added coordinates
                sites_total = []      #to store the corresponding specie
                good_structure = False

                for cycle2 in range(max2):
                    coordinates_tmp = deepcopy(coordinates_total)
                    sites_tmp = deepcopy(sites_total)
                    
            	    #Add specie by specie
                    for numIon, specie in zip(self.numIons, self.species):
                        numIon_added = 0
                        tol = max(0.5*Element(specie).covalent_radius, tol_m)

                        #Now we start to add the specie to the wyckoff position
                        for cycle3 in range(max3):
                            #Choose a random Wyckoff position for given multiplicity: 2a, 2b, 2c
                            ops = choose_wyckoff(self.wyckoffs, numIon-numIon_added) 
                            if ops is not False:
            	    	    #Generate a list of coords from ops
                                point = np.random.random(3)
                                #print('generating new points:', point)
                                coords = np.array([op.operate(point) for op in ops])
                                coords_toadd, good_merge = merge_coordinate(coords, cell_matrix, self.wyckoffs, self.sg, tol, self.PBC)
                                if good_merge:
                                    coords_toadd -= np.floor(coords_toadd) #scale the coordinates to [0,1], very important!
                                    #print('Adding: ', coords_toadd)
                                    if check_distance(coordinates_tmp, coords_toadd, sites_tmp, specie, cell_matrix, self.PBC):
                                        coordinates_tmp.append(coords_toadd)
                                        sites_tmp.append(specie)
                                        numIon_added += len(coords_toadd)
                                    if numIon_added == numIon:
                                        coordinates_total = deepcopy(coordinates_tmp)
                                        sites_total = deepcopy(sites_tmp)
                                        break
                        if numIon_added != numIon:
                            break  #need to repeat from the 1st species

                    if numIon_added == numIon:
                        #print(self.Msg6)
                        good_structure = True
                        break
                    else: #reset the coordinates and sites
                        coordinates_total = []
                        sites_total = []

                if good_structure:
                    final_coor = []
                    final_site = []
                    final_number = []
                    final_lattice = cell_matrix
                    for coor, ele in zip(coordinates_total, sites_total):
                        for x in coor:
                            final_coor.append(x)
                            final_site.append(ele)
                            final_number.append(Element(ele).z)
                    final_coor = np.array(final_coor)
                    final_lattice, final_coor = Permutation(final_lattice, final_coor, self.PB)
                    #print('before:  ', final_coor)
                    final_lattice, final_coor = Add_vacuum(final_lattice, final_coor)
                    #print('cell:  ', matrix2para(final_lattice))
                    #print(final_lattice)
                    #print(self.PB)
                    #print('length: ',len(self.wyckoffs)) 
                    self.lattice = final_lattice                    
                    self.coordinates = final_coor
                    self.sites = final_site                    
                    self.struct = Structure(final_lattice, final_site, np.array(final_coor))
                    self.spg_struct = (final_lattice, np.array(final_coor), final_number)
                    self.valid = True
                    return
        if degrees == 0: print("Wyckoff positions have no degrees of freedom.")
        self.struct = self.Msg2
        self.valid = False
        return self.Msg2

if __name__ == "__main__":
    #-------------------------------- Options -------------------------
    parser = OptionParser()
    parser.add_option("-s", "--spacegroup", dest="sg", metavar='sg', default=206, type=int,
            help="desired space group number: 1-230, e.g., 206")
    parser.add_option("-e", "--element", dest="element", default='Li', 
            help="desired elements: e.g., Li", metavar="element")
    parser.add_option("-n", "--numIons", dest="numIons", default=16, 
            help="desired numbers of atoms: 16", metavar="numIons")
    parser.add_option("-f", "--factor", dest="factor", default=3.0, type=float, 
            help="volume factor: default 3.0", metavar="factor")


    parser.add_option("-v", "--verbosity", dest="verbosity", default=0, type=int, help="verbosity: default 0; higher values print more information", metavar="verbosity")
    parser.add_option("-a", "--attempts", dest="attempts", default=10, type=int, 
            help="number of crystals to generate: default 1", metavar="attempts")
    parser.add_option("-o", "--outdir", dest="outdir", default="out", type=str, 
            help="Directory for storing output cif files: default 'out'", metavar="outdir")




    (options, args) = parser.parse_args()    
    element = options.element
    number = options.numIons
    numIons = []
    verbosity = options.verbosity
    attempts = options.attempts
    outdir = options.outdir

    if element.find(',') > 0:
        system = element.split(',')
        for x in number.split(','):
            numIons.append(int(x))
    else:
        system = [element]
        numIons = [int(number)]
    for i in range(attempts):
        numIons0 = np.array(numIons)
        sg = options.sg
        rand_crystal = random_crystal(options.sg, system, numIons0, options.factor)

        if rand_crystal.valid:
            #Output a cif file
            written = False
            try:
                mkdir(outdir)
            except: pass
            try:
                comp = str(rand_crystal.struct.composition)
                comp = comp.replace(" ", "")
                cifpath = outdir + '/' + comp + "_" + str(i+1) + '.cif'
                CifWriter(rand_crystal.struct, symprec=0.1).write_file(filename = cifpath)
                written = True
            except: pass
            #POSCAR output
            #rand_crystal.struct.to(fmt="poscar", filename = '1.vasp')

            #spglib style structure called cell
            ans = get_symmetry_dataset(rand_crystal.spg_struct, symprec=1e-1)['number']
            print('Space group  requested: ', sg, 'generated', ans)
            if written is True:
                print("    Output to "+cifpath)
            else:
                print("    Could not write cif file.")

            #Print additional information about the structure
            if verbosity > 0:
                print("Time required for generation: " + str(timespent) + "s")
                print(rand_crystal.struct)


        #If generation fails
        else: 
            print('something is wrong')
            print('Time spent during generation attempt: ' + str(timespent) + "s")
