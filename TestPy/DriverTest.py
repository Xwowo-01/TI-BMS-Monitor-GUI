import os

for root, dirs, files in os.walk(r"C:\Windows"):
    for f in files:
        if "vxlapi" in f.lower():
            print(os.path.join(root, f))