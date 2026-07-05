import os
import re

directory = 'c:/Repositories/ai-native-reqflow-POC/e2e/tests'

def cap_timeout(match):
    val = int(match.group(1))
    if val > 10000:
        return 'timeout: 10000'
    return match.group(0)

def cap_set_timeout(match):
    val = int(match.group(1))
    if val > 10000:
        return 'test.setTimeout(10000)'
    return match.group(0)

for root, _, files in os.walk(directory):
    for file in files:
        if file.endswith('.spec.ts'):
            path = os.path.join(root, file)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Replace timeout: X
            content = re.sub(r'timeout:\s*(\d+)', cap_timeout, content)
            
            # Replace test.setTimeout(X)
            content = re.sub(r'test\.setTimeout\((\d+)\)', cap_set_timeout, content)
            
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)

print("All explicit timeouts > 10000ms have been capped to 10000ms.")
