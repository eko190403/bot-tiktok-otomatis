import os
import re

try:
    import emoji
except ImportError:
    print("emoji library not found, doing nothing")
    exit(1)

def remove_emoji(text):
    return emoji.replace_emoji(text, replace='')

count = 0
for root, dirs, files in os.walk('.'):
    if '.git' in dirs:
        dirs.remove('.git')
    if '.venv' in dirs:
        dirs.remove('.venv')
        
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            cleaned_content = remove_emoji(content)
            
            if cleaned_content != content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(cleaned_content)
                print(f"Removed emojis from {filepath}")
                count += 1

print(f"Finished. Modified {count} files.")
