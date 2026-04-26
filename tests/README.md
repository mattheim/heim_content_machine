# Test Suite

This folder contains focused tests for the two main generation paths:

- `test_caption_generation.py` validates caption/content package assembly.
- `test_image_generation.py` validates image output handling and image prompt formatting.

Run everything from the project root:

```bash
python3 -m pytest heim_content_machine/tests
```

Run only caption tests:

```bash
python3 -m pytest heim_content_machine/tests/test_caption_generation.py
```

Preview live caption generation output:

```bash
python3 heim_content_machine/tests/run_caption_preview.py --runs 1
```

Optional model override:

```bash
python3 heim_content_machine/tests/run_caption_preview.py --model llama3 --runs 3
```

Run only image tests:

```bash
python3 -m pytest heim_content_machine/tests/test_image_generation.py
```
