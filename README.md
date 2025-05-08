# Obsidian2Anki

Export obsidian note to anki card efficiently

<img src="https://github.com/user-attachments/assets/323112b3-0257-4c76-ae60-fd958c388b0a" width="400px">

<img src="https://github.com/user-attachments/assets/bd772326-8ba2-4907-b692-5247182284e4" width="400px">

- [x] support the h4+ and the content.
- [x] support dark mode. 

# Anki Setup

## Connection

In Anki, navigate to Tools->Addons->AnkiConnect->Config, and change it to look like this:

```
{
    "apiKey": null,
    "apiLogPath": null,
    "webBindAddress": "127.0.0.1",
    "webBindPort": 8765,
    "webCorsOrigin": "http://localhost",
    "webCorsOriginList": [
        "http://localhost",
        "app://obsidian.md"
    ]
}
```

## NoteType

Utilize zero-md to render markdown note.

1. The fontsize

```html
<script type="module" src="https://cdn.jsdelivr.net/npm/zero-md@3?register"></script>

<zero-md>
	<script type="text/markdown">
{{正面}}
  </script>
</zero-md>
```

2. The backside

```html
{{FrontSide}}

<hr id=answer>

<zero-md>
  <script type="text/markdown">
{{背面}}
  </script>
</zero-md>
```

**3. delete the default note style**


