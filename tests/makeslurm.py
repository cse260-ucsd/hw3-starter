#!/usr/bin/env python3
#
# Generate a .slurm script that runs wave260 on Expanse (default),
# the Raspberry Pi cluster (--pi), or the Junkyard phone cluster (--phone).
#
#   cd tests
#   python makeslurm.py t1000.config -g 1x4,2x2           # -> t1000_n4.slurm
#   python makeslurm.py t1000.config -g 1x4,2x2 --pi      # -> t1000_n4pi.slurm
#   python makeslurm.py t1000.config -g 1x4,2x2 --phone   # -> t1000_n4phone.slurm
#   cd ../runs
#   sbatch ../tests/t1000_n4.slurm
#
import os
import sys
import argparse
import math

parser = argparse.ArgumentParser()
# required args
parser.add_argument("test", help='JSON config file')

# optional args
cluster = parser.add_mutually_exclusive_group()
cluster.add_argument("--pi", action='store_true', help='generate script for rpi, default is expanse')
cluster.add_argument("--phone", action='store_true', help='generate script for the phone (Junkyard) cluster, default is expanse')
parser.add_argument("-g", default=None, help= 'comma separated list of one or more geometries specified as rxc where there are r rows of processors by c columns of processors.  For example -g 4x4,8x2,2x8. If not specified, run the uniprocessor binary.' )
parser.add_argument("-n", type=int, default=None, help='matrix size')
parser.add_argument("-i", type=int, default=None, help='number of iterations')
parser.add_argument("-p", type=int, default=None, help='plot interval')
parser.add_argument("-k", action="store_true", default=False, help='disable communication')
args = parser.parse_args()

if (args.g == None):
    wavebin = "wave260uni"
    np0=1
    geolist=["1x1"]
else:
    wavebin = "wave260mpi"
    geolist = args.g.split(',')

    (py0, px0) = geolist[0].split('x')
    np0 = int(py0) * int(px0)
    for g in geolist:
        (py, px) = g.split('x')
        np = int(py) * int(px)
        if (np != np0):
            print("Error py ({}) * px ({}) = {} which is not equal to {} * {} n ({})".format(py, px, np, py0, px0, np0))
            sys.exit()

# extra wave260 flags, and the matching suffix for the script name
options = ""
suffix = ""
if args.n != None:
    options += " -n " + str(args.n)
if args.i != None:
    options += " -i " + str(args.i)
if args.p != None:
    options += " -p " + str(args.p)
    suffix += "_p" + str(args.p)
if args.k:
    options += " -k"
    suffix += "_k"
if args.pi:
    suffix += "pi"
if args.phone:
    suffix += "phone"


testfile = args.test
if (not os.path.exists(testfile)):
    print("Error: can't open {}".format(testfile))
    sys.exit()

testroot = os.path.basename(testfile)
testname_with_options = os.path.splitext(testroot)[0] + "_n" + str(np0) + suffix


cores = np0
if args.pi or args.phone:
    # every node offers a fixed number of MPI slots; the last node may be partly idle
    cores_per_node = 3 if args.pi else 4
    nodes = math.ceil(cores/cores_per_node)
else:
    nodes = math.ceil(cores/128)
    cores_per_node = int(cores / nodes)
    if (cores % nodes) != 0:
        print("Error: {} nodes cannot evenly divide {} cores".format(nodes, cores))
        sys.exit()

if args.pi:
    partition = "cse"
elif (cores <= 32):
    partition = "shared"
else:
    partition = "compute"

#
# give approv .75 GB/core
# really depends on the size of the grid but
# since the info is in the .config file, we don't know it here
#
mem_limit = int(0.55 * cores_per_node)


###### template slurm scripts ######
text_expanse = """#!/bin/bash
#SBATCH --job-name="../wave260"
#SBATCH --output="{testname_with_options}.%j.%N.out"
#SBATCH --partition={partition}
#SBATCH --nodes={nodes}
#SBATCH --ntasks-per-node={cores_per_node}
#SBATCH --mem={mem_limit}G
#SBATCH --account=sdp101
# #SBATCH --export=None
#SBATCH --export=ALL
#SBATCH -t 0:03:00
####   #SBATCH --mail-type=BEGIN,END,FAIL
####   #SBATCH --mail-user=your_email@ucsd.edu

# setup your environment

export SLURM_EXPORT_ENV=ALL
export MV2_USE_RDMA_CM=0
export MV2_HOMOGENEOUS_CLUSTER=1

module purge
module load cpu/0.17.3b  gcc/10.2.0/npcyll4  mvapich2/2.3.7/iyjtn3x
module load cmake/3.21.4/n5jtjsf
module load netcdf-c/4.8.1/yt65vte
module load ncview/2.1.8/znk6ds3
module load tau/2.30.2/auogdal
module load slurm

mkdir -p /expanse/lustre/scratch/{user}/temp_project/job_$SLURM_JOB_ID
"""

text_pi = """#!/bin/bash
#SBATCH --job-name="../wave260"
#SBATCH --output="{testname_with_options}.out"
#SBATCH --error="{testname_with_options}.err"
#SBATCH --partition={partition}
#SBATCH --nodes={nodes}
#SBATCH --ntasks-per-node={cores_per_node}
#SBATCH --mem={mem_limit}G

#SBATCH --export=ALL
#SBATCH -t 0:08:00
####   #SBATCH --mail-type=BEGIN,END,FAIL
####   #SBATCH --mail-user=your_email@ucsd.edu

# setup your environment

export SLURM_EXPORT_ENV=ALL

mkdir -p ./job_$SLURM_JOB_ID
"""

text_phone = """#!/bin/bash
#SBATCH --job-name="../wave260"
#SBATCH --output="{testname_with_options}.%j.%N.out"
#SBATCH --nodes={nodes}
#SBATCH --ntasks-per-node={cores_per_node}
#SBATCH -t 0:15:00

# keep MPI traffic on the phones' private network
export OMPI_MCA_btl_tcp_if_include=10.0.0.0/24
export OMPI_MCA_oob_tcp_if_include=10.0.0.0/24
"""

user = None
if args.pi:
    text = text_pi
    srun = "srun --mpi=pmix"
    build_dir = "build_pi"
elif args.phone:
    text = text_phone
    srun = "srun --mpi=pmix"
    build_dir = "build_phone"
else:
    user = os.getlogin()
    text = text_expanse
    srun = "srun --chdir /expanse/lustre/scratch/{}/temp_project/job_$SLURM_JOB_ID --mpi=pmi2".format(user)
    build_dir = "build_expanse"


#
# create output file
#
ofilename = testname_with_options + ".slurm"
print("Creating slurm script {}".format(ofilename))
with open(ofilename, "w") as f:
    f.write(text.format(testname_with_options=testname_with_options,
                        partition=partition,
                        nodes=nodes,
                        cores_per_node=cores_per_node,
                        mem_limit=mem_limit,
                        user=user))
    for g in geolist:
        (py, px) = g.split('x')
        f.write("\n{srun} -n {cores} $SLURM_SUBMIT_DIR/../{build_dir}/{wavebin} $SLURM_SUBMIT_DIR/../tests/{testfile} -y {py} -x {px}{options}\n".format(
            srun=srun, cores=cores, build_dir=build_dir, wavebin=wavebin,
            testfile=testfile, py=py, px=px, options=options))
