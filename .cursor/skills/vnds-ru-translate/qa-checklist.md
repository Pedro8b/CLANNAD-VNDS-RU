# Per-file QA checklist

Copy and tick while reviewing `script/FILE` vs `translated-ru/script/FILE`.

```
File: SEEN_____.scr
- [ ] python tools/vnds_pipeline.py check FILE → structure_ok true
- [ ] same line count as original
- [ ] non-text/choice lines byte-identical (tabs included)
- [ ] all @[speakers] from speakers.json (variables {$lnm*} unchanged)
- [ ] {$...} tokens preserved in text/choice
- [ ] choice branch count unchanged
- [ ] no English left in dialogue (except kept names)
- [ ] Tomoya/Sunohara masculine agreement
- [ ] Nagisa/Kyou/Ryou/Tomoyo/Fuko/Kotomi feminine agreement
- [ ] inner monologue vs spoken distinction kept
- [ ] scene meaning matches original
```

If any box fails: edit the Russian file, re-run `check`, then `set-status FILE qa_failed` only if you stop mid-file. When all pass: `set-status FILE approved`.
