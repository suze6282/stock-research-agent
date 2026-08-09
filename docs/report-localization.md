# Report localization

Stage 8 ships deterministic `zh-CN` and `en-US` templates. The locale is sealed
in the Request, template, JSON source, Markdown projection and checksum context.
Changing locale therefore creates a distinct report identity.

Only fixed labels and template statements are localized. Original excerpts,
legal wording, official names and stable metric, formula and document codes are
preserved. No translation provider or model is called.
