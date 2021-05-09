import os
import zipfile
from pprint import pprint as pp
from datetime import datetime

venv = "venv37"
app_files = [
            #"main.py",
             "tools.py",
             #"instagram_tools.py",
             #"twitter_tools.py",
             #"TweetProcess.py",
             #"imaging.py",
             "variables.py",
             "tweet_scheduler.py"]
app_dirs = [
            "logins",
            #"instagram_web_api",
            #"instagram_private_api"
            ]
output_dir = "packages"
site_package_blacklist = [
    "botocore",
    "dlib",
    "dlib-19.8.1.dist-info",
    "numpy",
    "numpy-1.18.3.dist-info",
    "PIL",
    "Pillow-8.1.0.dist-info",
    "numpy",
    "numpy-1.15.4.dist-info"
]
extra_packages_dir = "linux-site-packages"





def getAllFilePaths(root, dir_blacklist=tuple()):
    filepaths = []
    for path in os.listdir(root):

        fullpath = os.path.join(root, path)

        if os.path.isfile(fullpath):
            filepaths.append(fullpath)
        elif path not in dir_blacklist:
            filepaths += getAllFilePaths(fullpath)

    return filepaths


site_packages_dir = os.path.join(venv, "Lib", "site-packages")
timestr = datetime.utcnow().strftime("%Y-%m-%d %H-%M-%S")
zipname = os.path.join(output_dir, "{} {}.zip".format(os.getcwd().split(os.sep)[-1], timestr))
if not os.path.exists(output_dir):
    os.mkdir(output_dir)

z = zipfile.ZipFile(zipname, "w", zipfile.ZIP_DEFLATED)

# Add files
for file in app_files:
    z.write(filename=file)

# Add directories
for dir in app_dirs:
    files_in_dir = getAllFilePaths(dir)
    for file in files_in_dir:
        z.write(filename=file)


# Add site packages in top level
paths_in_sps = getAllFilePaths(site_packages_dir, dir_blacklist=tuple(site_package_blacklist))
for path in paths_in_sps:
    c_path = path[len(site_packages_dir):].lstrip(os.sep)
    z.write(filename=path, arcname=c_path)


# Add all site packages from extra dir
extra_packages_paths = getAllFilePaths(extra_packages_dir)
for path in extra_packages_paths:
    c_path = path[len(extra_packages_dir):].lstrip(os.sep)
    z.write(filename=path, arcname=c_path)


z.close()
