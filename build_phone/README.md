# Phone Cluster Guide

## Install


## Set Up CMake

```sh
cd build_phone
cmake ..
```

## Compile

```sh
cmake --build .
# or
make
```

## Run (example)

```sh
cd tests
python3 makeslurm.py t1000.config --phone -g 1x4,2x2
cd ../runs
sbatch ../tests/t1000_n4phone.slurm
```
