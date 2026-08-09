# Prompt-injection defense

All document content is untrusted data. `prompt-injection-rules-v1` deterministically marks common
override language, system-prompt imitation, credential requests, Tool-call syntax and exfiltration
URLs in bounded text. Marking does not delete evidence and does not execute an instruction. The
same parser output remains available for citation and audit.

Content cannot change parser limits, security/snapshot/as-of filters, Tool permissions, provider
configuration, network gates or system configuration. HTML scripts and active resources are
suppressed; PDF actions and attachments are ignored; JSON strings remain data. Tool/API are
read-only and不得隐式刷新. No parser imports HTTP or Session code. Stage 6 不调用大模型, implements
no Agent/MCP runtime and produces no investment report, target price, trade or portfolio advice.
