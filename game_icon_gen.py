import fontforge
import psMat
from pathlib import Path
import json
import sys
import os
import argparse
import xml.etree.ElementTree as ET
import tempfile
import math

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return None

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def create_clipped_base_svg(base_svg_path, output_path, weapon_type):
    """
    Just copy the base SVG - we'll do the clipping in FontForge using path operations.
    """
    import shutil
    shutil.copy(base_svg_path, output_path)
    return output_path

def main():
    parser = argparse.ArgumentParser(description="Generate font from weapon SVGs.")
    parser.add_argument('--base_folder', type=str, help="Path to base weapon SVGs folder (containing 1.svg to 7.svg)")
    parser.add_argument('--variant_folder', type=str, help="Path to variant SVGs folder (containing 100.svg, 101.svg, etc.)")
    parser.add_argument('--output_font', type=str, help="Output font path (e.g., weapons.ttf)")
    args = parser.parse_args()

    config = load_config()
    if config:
        print("Loaded config from config.json")
        base_folder = args.base_folder or config.get("base_folder")
        variant_folder = args.variant_folder or config.get("variant_folder")
        output_font = args.output_font or config.get("output_font")
    else:
        base_folder = args.base_folder or input("Enter path to base weapon SVGs folder (containing 1.svg to 7.svg): ").strip()
        variant_folder = args.variant_folder or input("Enter path to variant SVGs folder (containing 100.svg, 101.svg, etc.): ").strip()
        output_font = args.output_font or input("Enter output font path (e.g., weapons.ttf): ").strip()

    # Validate folders
    if not Path(base_folder).is_dir():
        print("Base folder does not exist.")
        sys.exit(1)
    if not Path(variant_folder).is_dir():
        print("Variant folder does not exist.")
        sys.exit(1)

    # Scan base types
    types = []
    for t in range(1, 8):
        p = Path(base_folder) / f"{t}.svg"
        if p.exists():
            types.append(t)

    if not types:
        print("No base SVGs found (1.svg to 7.svg).")
        sys.exit(1)

    # Build all 100 variants per weapon type (00-99)
    # Scan for available variant SVGs
    available_variants = {}
    for f in Path(variant_folder).glob("*.svg"):
        name = f.stem
        if len(name) == 3 and name.isdigit():
            weapon_id = int(name)
            if 100 <= weapon_id <= 799:
                available_variants[weapon_id] = f

    # Create all weapon IDs from 100-799 based on available types
    weapon_ids = []
    for t in types:
        for subtype in range(100):
            weapon_id = t * 100 + subtype
            weapon_ids.append(weapon_id)

    print(f"\nWill generate {len(weapon_ids)} glyphs (all variants 00-99 for types {types})")
    print(f"Found {len(available_variants)} variant SVG files")
    
    # Print sample associations
    print("\nSample associations:")
    for i, weapon_id in enumerate(sorted(weapon_ids)[:10]):
        t = weapon_id // 100
        subtype = weapon_id % 100
        has_variant = "✓" if weapon_id in available_variants else "✗"
        print(f"ID {weapon_id}: type {t} (base {t}.svg), subtype {subtype:02d} {has_variant}")
    if len(weapon_ids) > 10:
        print(f"... and {len(weapon_ids) - 10} more")

    # Confirm
    confirm = input("\nProceed to generate font? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Aborted.")
        sys.exit(0)

    # Save config
    new_config = {
        "base_folder": base_folder,
        "variant_folder": variant_folder,
        "output_font": output_font
    }
    save_config(new_config)
    print("Config saved to config.json")

    # Create font
    font = fontforge.font()
    font.encoding = "UnicodeFull"
    font.em = 256
    font.ascent = 256
    font.descent = 0

    codepoint = 0xE000
    mapping = {}
    
    # Create temp directory for clipped SVGs
    temp_dir = tempfile.mkdtemp()

    scale_factor = 0.5
    padding = 8
    variant_size = 256 * scale_factor
    cutout_size = int(padding + variant_size + padding)

    for weapon_id in weapon_ids:  # Process in order 100-799
        t = weapon_id // 100
        subtype = weapon_id % 100
        base_svg = str(Path(base_folder) / f"{t}.svg")
        
        # Check if variant exists
        has_variant = weapon_id in available_variants
        var_svg = str(available_variants[weapon_id]) if has_variant else None

        glyph = font.createChar(codepoint)
        
        # Import base SVG for left half
        glyph.importOutlines(base_svg)
        glyph.simplify()
        glyph.correctDirection()
        
        # Apply offset corrections for types 3-6
        x_offset = 256 if t in [3, 4, 5, 6] else 0
        y_offset = -256 if t == 4 else 0
        
        if x_offset != 0 or y_offset != 0:
            offset_mat = psMat.translate(x_offset, y_offset)
            glyph.transform(offset_mat)
        
        # Prepare flipped right half
        temp = font.createChar(-1, f"temp_flip_{weapon_id}")
        temp.importOutlines(base_svg)
        temp.simplify()
        temp.correctDirection()
        
        if x_offset != 0 or y_offset != 0:
            offset_mat = psMat.translate(x_offset, y_offset)
            temp.transform(offset_mat)
        
        if has_variant:
            if t in [1,2,3,4,5,6]:
                # Define variant positions for left and right (pre-flip)
                if t == 1:
                    # Bottom left on right side: pre-flip bottom right in temp
                    variant_x_right = 256 - variant_size - padding
                    variant_y_right = padding
                    # Symmetric for left half: bottom right
                    variant_x_left = 256 - variant_size - padding
                    variant_y_left = padding
                elif t in [2,3,4]:
                    # Top left on right side: pre-flip top right in temp
                    variant_x_right = 256 - variant_size - padding
                    variant_y_right = 256 - variant_size - padding
                    # Symmetric for left half: top right
                    variant_x_left = 256 - variant_size - padding
                    variant_y_left = 256 - variant_size - padding
                elif t == 5:
                    # Top right on right side: pre-flip top left in temp
                    variant_x_right = padding
                    variant_y_right = 256 - variant_size - padding
                    # Symmetric for left half: top left
                    variant_x_left = padding
                    variant_y_left = 256 - variant_size - padding
                elif t == 6:
                    # Top left on right side: pre-flip top right in temp
                    variant_x_right = 256 - variant_size - padding
                    variant_y_right = 256 - variant_size - padding
                    # Symmetric for left half: top right
                    variant_x_left = 256 - variant_size - padding
                    variant_y_left = 256 - variant_size - padding
                
                # Add variant to glyph (left half)
                temp_variant = font.createChar(-1, f"temp_variant_left_{weapon_id}")
                temp_variant.importOutlines(var_svg)
                temp_variant.simplify()
                temp_variant.correctDirection()
                
                scale_mat = psMat.scale(scale_factor, scale_factor)
                temp_variant.transform(scale_mat)
                
                variant_mat = psMat.translate(variant_x_left, variant_y_left)
                temp_variant.transform(variant_mat)
                
                glyph.layers[1] = glyph.layers[1] + temp_variant.layers[1]
                glyph.removeOverlap()
                font.removeGlyph(temp_variant)
                
                # Add variant to temp (right half pre-flip)
                temp_variant = font.createChar(-1, f"temp_variant_right_{weapon_id}")
                temp_variant.importOutlines(var_svg)
                temp_variant.simplify()
                temp_variant.correctDirection()
                
                scale_mat = psMat.scale(scale_factor, scale_factor)
                temp_variant.transform(scale_mat)
                
                variant_mat = psMat.translate(variant_x_right, variant_y_right)
                temp_variant.transform(variant_mat)
                
                temp.layers[1] = temp.layers[1] + temp_variant.layers[1]
                temp.removeOverlap()
                font.removeGlyph(temp_variant)
            elif t == 7:
                # Center without square, just add variant for both halves
                variant_x = 128 - (variant_size / 2)
                variant_y = 128 - (variant_size / 2)
                
                # For glyph (left half)
                temp_variant = font.createChar(-1, f"temp_variant_left_{weapon_id}")
                temp_variant.importOutlines(var_svg)
                temp_variant.simplify()
                temp_variant.correctDirection()
                
                scale_mat = psMat.scale(scale_factor, scale_factor)
                temp_variant.transform(scale_mat)
                
                variant_mat = psMat.translate(variant_x, variant_y)
                temp_variant.transform(variant_mat)
                
                glyph.layers[1] = glyph.layers[1] + temp_variant.layers[1]
                glyph.removeOverlap()
                font.removeGlyph(temp_variant)
                
                # For temp (right half pre-flip)
                temp_variant = font.createChar(-1, f"temp_variant_right_{weapon_id}")
                temp_variant.importOutlines(var_svg)
                temp_variant.simplify()
                temp_variant.correctDirection()
                
                scale_mat = psMat.scale(scale_factor, scale_factor)
                temp_variant.transform(scale_mat)
                
                variant_mat = psMat.translate(variant_x, variant_y)
                temp_variant.transform(variant_mat)
                
                temp.layers[1] = temp.layers[1] + temp_variant.layers[1]
                temp.removeOverlap()
                font.removeGlyph(temp_variant)
            else:
                # For other types, add variant without position change
                glyph.importOutlines(var_svg)
                glyph.simplify()
                glyph.correctDirection()
                
                temp.importOutlines(var_svg)
                temp.simplify()
                temp.correctDirection()

        # Transform temp to right half
        mat = psMat.compose(psMat.scale(-1.0, 1.0), psMat.translate(512.0, 0.0))
        temp.transform(mat)
        
        # Merge flipped version into main glyph
        glyph.layers[1] = glyph.layers[1] + temp.layers[1]
        font.removeGlyph(temp)

        # Clean up and correct directions to ensure proper filling and holes
        glyph.removeOverlap()
        glyph.correctDirection()

        glyph.width = 512
        glyph.glyphname = f"weapon{weapon_id}"

        mapping[weapon_id] = f"U+{codepoint:04X}"
        codepoint += 1
    
    # Clean up temp directory
    import shutil
    shutil.rmtree(temp_dir)

    # Generate font
    font.generate(output_font)
    print(f"\nFont generated at {output_font}")

    # Generate WOFF for HTML embedding
    woff_path = "weapons.woff"
    font.generate(woff_path)
    print(f"WOFF font generated at {woff_path}")

    # Print mappings
    print("\nConversion Table (ID to Unicode):")
    for weapon_id, ucode in sorted(mapping.items()):
        print(f"{weapon_id}: {ucode}")

    # Save mappings to file
    with open("mappings.json", 'w') as f:
        json.dump(mapping, f, indent=4)
    print("Mappings saved to mappings.json")

    # Render all symbols in an HTML file
    codepoints = [int(ucode[2:], 16) for ucode in sorted(mapping.values(), key=lambda x: int(x[2:], 16))]
    num_glyphs = len(codepoints)
    cols = 20
    rows = math.ceil(num_glyphs / cols)

    html_content = """
<html>
<head>
<style>
@font-face {
    font-family: 'Weapons';
    src: url('weapons.woff') format('woff');
}
.grid {
    display: grid;
    grid-template-columns: repeat(20, 100px);
    gap: 5px;
    font-family: 'Weapons';
    font-size: 48px;
    text-align: center;
}
.grid div {
    width: 100px;
    height: 50px;
    line-height: 50px;
    overflow: hidden;
}
</style>
</head>
<body>
<div class="grid">
"""

    for cp in codepoints:
        html_content += f"<div>{chr(cp)}</div>\n"

    html_content += """
</div>
</body>
</html>
"""

    render_path = "glyphs_render.html"
    with open(render_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"Rendered all symbols to {render_path}. Open in a browser to view.")

if __name__ == "__main__":
    main()