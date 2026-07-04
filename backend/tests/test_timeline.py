import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from api import get_sdi_timeline

try:
    result = get_sdi_timeline()
    print(f"Success! Length of timeline: {len(result)}")
    for p in result:
        print(p)
except Exception as e:
    print(f"Error: {e}")
