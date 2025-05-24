from platformdirs import user_data_dir
import pathlib
import os

package_dir = pathlib.Path(__file__).parent.absolute()
data_dir = user_data_dir("atlasserver", "AtlasServer-Core")
os.makedirs(data_dir, exist_ok=True)