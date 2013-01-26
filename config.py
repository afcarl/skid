from path import path
ROOT = path('~/.skid').expand()    # feel free to use environment variables

# test skid repository
#ROOT = path('~/.skid-test').expand()    # feel free to use environment variables

CACHE = ROOT / 'marks'
REMOTE = 'login.clsp.jhu.edu:~/papers'


if not ROOT.exists():
    ROOT.mkdir()

if not CACHE.exists():
    CACHE.mkdir()
