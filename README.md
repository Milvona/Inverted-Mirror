# Minecraft Bedrock Inverted Floating Library

This project procedurally generates a Bedrock Edition `.mcstructure` for an inverted floating magical library, then renders simple PNG previews by reading the generated structure file back from disk.

## Generate

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts\generate_inverted_library.py
python scripts\validate_mcstructure.py out\inverted_library.mcstructure
python scripts\render_structure_preview.py out\inverted_library.mcstructure out\previews
```

Outputs:

- `out/inverted_library.mcstructure`
- `out/previews/iso.png`
- `out/previews/front.png`
- `out/previews/side.png`
- `out/previews/top.png`

## Structure Notes

The first version intentionally uses stable full blocks and simple Bedrock little-endian NBT:

- Size: `96 x 128 x 96`
- Three open library floors at `y=34`, `y=58`, and `y=82`
- 2.5-turn spiral walkway from `y=28` to `y=88`
- 30 colored lantern nodes around the outer spiral
- Central colored glowing crystal core from `y=44` to `y=76`
- Oxidized copper spire from `y=92` to `y=124`
- Inverted blue crystal cone from `y=4` to `y=30`

## Preview

The bundled preview renderer is a lightweight Pillow voxel renderer. It does not use Minecraft textures, but it color-codes bookshelves, stone, wood, copper, glowing blocks, and glass crystals so the silhouette can be checked quickly.

You can also inspect `out/inverted_library.mcstructure` with MCStructure Preview for a more specialized external preview workflow.

## Import Into Minecraft Bedrock

Copy `out/inverted_library.mcstructure` into a world's `structures` folder. If the folder does not exist, create it.

Typical Windows Bedrock world path:

```text
%LOCALAPPDATA%\Packages\Microsoft.MinecraftUWP_8wekyb3d8bbwe\LocalState\games\com.mojang\minecraftWorlds\<world_id>\structures\
```

After copying the file, load the world and run:

```text
/structure load inverted_library ~ ~ ~
```

The structure is 96 blocks wide and 128 blocks tall, so load it in open air with enough clearance.
