import os
import glob

files = glob.glob('**/admin.py', recursive=True)

for file in files:
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if '.objects.unscoped()' in content:
        content = content.replace('.objects.unscoped()', '.unscoped.all()')
        with open(file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Fixed {file}")

print("Done")
