with open('reading-page.js', 'r', encoding='utf-8') as f:
    js = f.read()

print("Length of reading-page.js:", len(js))
# Print the last 4000 characters of reading-page.js
print("\n--- LAST 4000 CHARACTERS OF reading-page.js ---")
print(js[-4000:])
