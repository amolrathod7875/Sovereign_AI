#!/usr/bin/env python3
# Simple script to check and fix vision.py

# Read the file
with open('backend/app/api/vision.py', 'r') as f:
    content = f.read()

# Check for duplicate return statements
lines = content.split('\n')
print("Checking for duplicate return statements...")

# Find all occurrences of 'result = payload[\"result\"]'
result_lines = []
for i, line in enumerate(lines):
    if 'result = payload["result"]' in line:
        result_lines.append(i)

print(f'Found {len(result_lines)} occurrences of result = payload[\"result\"]')

if len(result_lines) > 1:
    print("DUPLICATE FOUND! Removing duplicate...")
    
    # Keep lines up to the first occurrence
    new_lines = lines[:result_lines[0]]
    
    # Skip the duplicate
    for i in range(1, len(result_lines)):
        # Find where this duplicate ends
        # Look for the closing paren or the next line with less indentation
        j = result_lines[i]
        while j < len(lines) and (lines[j].strip() == '' or 
                                  lines[j].strip().startswith(('return', 'raise', 'except', 'finally')) or
                                  len(lines[j]) - len(lines[j].lstrip()) >= len(lines[result_lines[0]])):
            j += 1
        # Keep everything up to this line
        new_lines.extend(lines[result_lines[i]:j])
    
    # Write back
    with open('backend/app/api/vision.py', 'w') as f:
        f.write('\n'.join(new_lines))
    
    print("Fixed vision.py")
else:
    print("No duplicate found in vision.py")
