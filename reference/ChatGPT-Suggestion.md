Mike — fair criticism. I should have started with this earlier instead of treating it like an optional add-on. I’ll explain it directly and clearly.

## The Core Problem You’re Fighting

Prompt-only control will **never fully lock a visual style** with diffusion models. Even a perfect prompt produces drift because the model samples from a distribution.

That’s why your images look **80–90% correct but never identical**.

Studios solve this by **anchoring the generation with a reference image**, not just text.

This is called **reference image conditioning**.

---

# What Reference Image Conditioning Is

Instead of sending only text like:

```
prompt: "Blizzard style salt elemental..."
```

you send **one or more example images** along with the prompt.

The model then **conditions its generation on those images**.

So instead of interpreting “Blizzard style” abstractly, it literally sees:

* the crystal shapes
* the lighting style
* the armor design
* the baby elemental proportions

and matches them.

Think of it as:

```
style = example images
content = prompt
```

---

# Why This Fixes Your Problem

Right now the model guesses what you mean by:

```
Blizzard style
crystal facets
WoW promotional art
```

With reference conditioning it instead does:

```
match THIS visual style
but change the scene
```

Which is exactly what you want for **podcast episode artwork**.

---

# What This Looks Like in the OpenAI API

You include images as **input images**.

Example structure:

```json
POST /v1/images/edits
```

```json
{
  "model": "gpt-image-1",
  "image": [
    "reference_style_1.png",
    "reference_style_2.png"
  ],
  "prompt": "Inside a treasure cave baby salt elementals host a chaotic podcast..."
}
```

Those reference images should be your **best previous outputs**.

For example:

* your logo image
* your best cave scene
* a baby elemental sprite sheet

The model will then **inherit that style automatically**.

---

# What Your Pipeline Would Look Like

Claude Code should assemble requests like this:

```
reference images (fixed set)
+
scene prompt (episode specific)
```

Example:

```
reference_images = [
  "salt_elemental_style_01.png",
  "salt_elemental_style_02.png",
  "salt_elemental_style_03.png"
]

prompt = "Episode scene description..."
```

---

# Best Reference Images To Use

From the ones you showed earlier, the strongest anchors would be:

1. the **logo image**
2. the **sprite sheet**
3. one **cave episode scene**

Three images is usually enough.

---

# Why This Is the Real Solution

Prompt engineering tries to describe a style.

Reference conditioning **shows the model the style**.

That eliminates most drift.

---

# One Important Limitation

The `/images/generations` endpoint you are using **does not support reference conditioning**.

You must use:

```
/v1/images/edits
```

because edits allow image inputs.

That’s the main difference.

---

# The Practical Result

Once you do this, you’ll see:

* crystal shapes stay consistent
* baby elementals stop mutating
* armor stays the same
* lighting stays similar
* style becomes stable across episodes

In other words: **much closer to your original images**.

---

If you want, I can also show you the **exact Claude Code function** that builds this request so your episode generator can automatically include the style references.
