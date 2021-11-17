from gym.wrappers import Monitor
import glob
import io, os
import base64
from IPython.display import HTML
from IPython import display as ipythondisplay

## modified from https://colab.research.google.com/drive/1flu31ulJlgiRL1dnN2ir8wGh9p7Zij2t#scrollTo=TCelFzWY9MBI

def show_video():
  home = os.path.expanduser('~')
  ex_path = '/Documents/Python/BerkeleyDRL_fall2021/hw1'
  mp4list = glob.glob(home + ex_path + '/content/video/*.mp4')
  if len(mp4list) > 0:
    mp4 = mp4list[0]
    video = io.open(mp4, 'r+b').read()
    encoded = base64.b64encode(video)
    ipythondisplay.display(HTML(data='''<video alt="test" autoplay 
                loop controls style="height: 400px;">
                <source src="data:video/mp4;base64,{0}" type="video/mp4" />
             </video>'''.format(encoded.decode('ascii'))))
  else: 
    print("Could not find video")
    

def wrap_env(env):
  home = os.path.expanduser('~')
  ex_path = '/Documents/Python/BerkeleyDRL_fall2021/hw1'
  env = Monitor(env, home + ex_path + '/content/video', force=True)
  return env