# Smart Output recovery hotfix

This hotfix adds conservative recovery for a terminal `CR_OUTPUT` control when a provider prepends harmless prose or omits one final closing bracket. The recovered JSON still passes the existing strict Smart Output schema and runtime reference/authority validation. Trailing prose after the control remains rejected.
