# promptry

Regression protection for LLM pipelines.

Track prompt versions, run eval suites, detect drift, catch regressions before they hit production.

## Install

```bash
pip install promptry
```

## Quick start

```python
from promptry import track

# one line in your existing pipeline
prompt = track("You are a helpful assistant...", "rag-qa")
response = llm.chat(system=prompt, ...)
```

```bash
# see what's tracked
promptry prompt list

# diff versions
promptry prompt diff rag-qa 1 2
```

## Status

Work in progress.
