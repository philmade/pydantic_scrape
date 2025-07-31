# Chawan Documentation Index

## Core API References
- **API.html** - Complete command API reference (main reference)
- **Architecture.html** - How chawan works internally
- **ConfigurationofChawan.html** - Configuration options and settings

## Key API Interfaces

### Client (globalThis)
- `quit()` - Exit browser
- `pager` - Pager object
- `line` - Line editor
- `config` - Configuration access

### Pager (pager)
- `load(url)` - Navigate to URL (with prompt)
- `loadSubmit(url)` - Load URL directly 
- `gotoURL(url, options)` - Direct navigation
- `externCapture(cmd)` - Capture external command output
- `buffer` - Current buffer object

### Buffer (pager.buffer)
- `click()` - Click element under cursor
- `cursorNextLink()`, `cursorPrevLink()` - Navigate between links
- `cursorUp()`, `cursorDown()`, etc. - Cursor movement
- `url` - Current buffer URL (URL object)
- `hoverLink`, `hoverTitle` - Element info under cursor
- `cursorx`, `cursory` - Current cursor position

### LineEdit (line)
- `submit()` - Submit form/input
- `cancel()` - Cancel operation
- `insertText(text)` - Insert text
- `clearLine()` - Clear input

## Navigation Strategy
1. Use `pager.loadSubmit(url)` for initial navigation
2. Use `buffer.cursorNextLink()` to move between links
3. Use `buffer.click()` to activate links/elements
4. Use `pager.externCapture()` to get page content
5. Use `buffer.url.href` to get current URL

## Content Extraction Strategy
- `pager.externCapture("echo content")` - Test command execution
- Could potentially capture buffer content via external commands
- May need to use dump mode with separate process for reliable content

## Form Interaction
- Move cursor to form elements
- Use line editor commands for input
- Use `line.submit()` for form submission

## Process Model
- Main process (pager) handles UI and commands
- Buffer processes handle page loading and rendering
- Communication via IPC between processes
- JavaScript API provides bridge between processes