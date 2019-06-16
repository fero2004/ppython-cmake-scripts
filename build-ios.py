#!/usr/bin/env python3
import subprocess, os, argparse, json

# Create dummy namespace to store arguments in.
class Args: pass
args = Args()

cpus = os.cpu_count()

argparser = argparse.ArgumentParser(description='Build Python for iOS.')
argparser.add_argument('--build-dir', default='built-ios')
argparser.add_argument('--install-dir', default='install')
argparser.add_argument('--arch', default='arm64', choices=['arm64', 'x86_64'])
argparser.add_argument('--sim-device', default='iPhone 6')
argparser.add_argument('--runtime-ver', default='12.2')
argparser.add_argument('--coresimulator_path', default='{}/Library/Developer/CoreSimulator/Devices'.format(os.environ['HOME']))
argparser.parse_args(namespace=args)

# Build all of the paths we need.
darwin_build_loc = os.path.join(args.build_dir, 'darwin-x86_64-freeze_importlib')
sim_build_loc = os.path.join(args.build_dir, 'ios-x86_64')
if args.arch != 'x86_64':
    sim_build_loc += '-sysconfig'

base_cmake_dir = os.path.abspath(os.getcwd())

print("Building for {} on iOS {}".format(args.arch, args.runtime_ver))

# Run a host build for _freeze_importlib, which is utilized during the crosscompile builds.
os.makedirs(darwin_build_loc, exist_ok=True)
subprocess.run(['cmake', base_cmake_dir], cwd=darwin_build_loc, check=True)
subprocess.run(['make', '_freeze_importlib', '-j{}'.format(cpus)], cwd=darwin_build_loc, check=True)

# Look for the specified simulator device, and bail if we can't find it.
print('Looking for Simulator "{}"'.format(args.sim_device))
device_json = subprocess.run(['xcrun', 'simctl', 'list', '--json'], check=True, capture_output=True)
devices = json.loads(device_json.stdout)
runtime = devices['devices']['com.apple.CoreSimulator.SimRuntime.iOS-{}'.format(args.runtime_ver.replace('.', '-'))]
device_udid = [dev['udid'] for dev in runtime if dev['name'] == args.sim_device and dev['isAvailable']][0]
if device_udid:
    print('Found {}!'.format(device_udid))
else:
    print('Couldn\'t find a UDID for {}, aborting.'.format(args.sim_device))

# Now that we found the simulator, we can build up the path to its data
# directory, so we can find the generated update_sysconfig files.
coresim_path = os.path.join(args.coresimulator_path, device_udid, 'data')
assert os.path.exists(coresim_path), 'The specified CoreSimulator (%s) path and device UDID does not match.' % coresim_path

print('Shutting down already-booted simulators...')
subprocess.run(['xcrun', 'simctl', 'shutdown', 'all'], check=True)

print('Booting up {}...'.format(device_udid))
subprocess.run(['xcrun', 'simctl', 'boot', device_udid], check=True)

int_build_options = ['-DCMAKE_STATIC_DEPENDENCIES=ON']
final_build_options = ['-DBUILD_LIBPYTHON_SHARED=ON', '-DBUILD_EXTENSIONS_AS_BUILTIN=ON', '-DCMAKE_INSTALL_PREFIX={}'.format(args.install_dir), '-DIOS_CORESIM_PATH={}'.format(coresim_path)]

# Depending on if we're just doing a simulator build or an arm64 build,
# generate the update_sysconfig files and install them.
try:
    native_exports_loc = os.path.abspath(os.path.join(darwin_build_loc, 'CMakeBuild/libpython/NativeExports.cmake'))
    os.makedirs(sim_build_loc, exist_ok=True)
    if args.arch == 'x86_64':
        subprocess.run(['cmake', '-DCMAKE_SYSTEM_NAME=iOS', '-DCMAKE_OSX_ARCHITECTURES=x86_64', '-DCMAKE_OSX_SYSROOT=iphonesimulator', '-DIMPORT_NATIVE_EXECUTABLES={}'.format(native_exports_loc), *final_build_options, base_cmake_dir], cwd=sim_build_loc, check=True)
        subprocess.run(['make', 'install', '-j{}'.format(cpus)], cwd=sim_build_loc, check=True)
    else:
        subprocess.run(['cmake', '-DCMAKE_SYSTEM_NAME=iOS', '-DCMAKE_OSX_ARCHITECTURES=x86_64', '-DCMAKE_OSX_SYSROOT=iphonesimulator', '-DIMPORT_NATIVE_EXECUTABLES={}'.format(native_exports_loc), *int_build_options, base_cmake_dir], cwd=sim_build_loc, check=True)
        subprocess.run(['make', '-j{}'.format(cpus)], cwd=sim_build_loc, check=True)
    
        device_build_loc = os.path.join(args.build_dir, 'ios-arm64')
        os.makedirs(device_build_loc, exist_ok=True)

        subprocess.run(['cmake', '-DCMAKE_SYSTEM_NAME=iOS', '-DCMAKE_OSX_ARCHITECTURES={}'.format(args.arch), '-DCMAKE_OSX_SYSROOT=iphoneos', '-DIMPORT_NATIVE_EXECUTABLES={}'.format(native_exports_loc), *final_build_options, base_cmake_dir], cwd=device_build_loc, check=True)
        subprocess.run(['make', 'install', '-j{}'.format(cpus)], cwd=device_build_loc, check=True)
finally:
    subprocess.run(['xcrun', 'simctl', 'shutdown', device_udid])