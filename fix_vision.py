#!/usr/bin/env python3
# Simple script to fix duplicate return in vision.py

# Read the file
with open('backend/app/api/vision.py', 'r') as f:
    lines = f.readlines()

# Find the duplicate return statement
# We need to remove the duplicate "result = payload['result']" line

# Find the first "result = payload['result']"
first_result_idx = -1
for i, line in enumerate(lines):
    if line.strip() == 'result = payload["result"]':
        first_result_idx = i
        break

# Find the duplicate (second occurrence)
duplicate_idx = -1
for i, line in enumerate(lines):
    if i > first_result_idx and line.strip() == 'result = payload["result"]':
        duplicate_idx = i
        break

if duplicate_idx != -1:
    # Remove everything from duplicate_idx to the end
    new_lines = lines[:duplicate_idx]
    
    # Write back
    with open('backend/app/api/vision.py', 'w') as f:
        f.writelines(new_lines)
    
    print(f"Fixed vision.py: removed duplicate starting at line {duplicate_idx + 1}")
else:
    print("No duplicate found in vision.py")
