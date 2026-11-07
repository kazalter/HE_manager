# Interaction recovery

Normal completion returns to the configured looping idle variant. OnFinishAnim(0) alone must never freeze the character. Persistent card/menu state belongs to the Lua controller configuration, not a guess based on curve end values. Hint visibility and click playback share resolveHitMotion; a missing or blocked numbered action must not play a random sibling. Hit meshes participate geometrically even when transparent.

35 recovered controller configs are versioned in configs/ and installed alongside the HDD models. Existing differing configs are preserved and reported as an error. Restore them after copying model assets with:

```sh
python3 install_configs.py configs /mnt/hdd/azurlane-l2dviewer/models
node tests/interaction.test.mjs
node tests/card-recovery.test.mjs /mnt/hdd/azurlane-l2dviewer/models/lafeiii/lafeiii_3
```

The card regression uses the actual Cubism motion queue, model parameters, and Lua controller entries. It opens the cards, drags each selection into its trigger range, verifies idle4/idle5/idle6 continue moving, closes the cards, and verifies another interaction remains possible. It does not replace a browser pointer/geometry test.

Config generation was fixed in the retained Windows L2Dviewer unpacking repository, commit 036dbd2: match painting case-insensitively, parse escaped quotes, and select ship_l2d entries by the exact template references rather than assuming skin_id*100. Source inputs are the existing .tmp/lua/CN snapshot and each model's Animator idle routing.

The existing snapshot still lacks referenced entries for ten skins: aijier_4, bunao_3, dewenjun_2, feiteliekaer_4, fengyun_4, gangyishawa_3, pulimaosi_3, sailimiye_2, shuixinghao_2, suweiaitongmeng_3. No partial controller was installed for them. They require complete matching Lua data before claiming full game-equivalent behavior.
