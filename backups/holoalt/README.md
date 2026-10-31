# holoalt pre-upgrade backup (2026-10-31)

This directory contains an **AES-256-GCM encrypted** backup of the Unity project `holoalt`, created before upgrading from Unity **2022.3.30f1**.

The GitHub repository containing this file is **public**. The unencrypted source and decryption key are not committed. The encrypted archive is stored using Git LFS.

## Files
- `holoalt_preupgrade_20261031_233003.zip.aesgcm`: encrypted original ZIP (433,550,587 bytes).
- `decrypt_holoalt.py`: Python restoration/integrity-verification helper.

Original ZIP SHA-256:
`14f71c96c619258795fa7ec01dcd38145e59ac2dc29bbcbb72b584ed154b63d4`

## Restore
1. Download this directory with Git LFS. Install `git-lfs`, clone the repository, then run `git lfs pull` if necessary.
2. Install Python and the `cryptography` package (`python -m pip install cryptography`).
3. Run:
   `python decrypt_holoalt.py holoalt_preupgrade_20261031_233003.zip.aesgcm holoalt_restored.zip`
4. Enter the **private 64-character hexadecimal key** when prompted. This key is **not on GitHub** and must be retained separately.
5. Extract `holoalt_restored.zip` into a NEW project directory. Open it with Unity 2022.3.30f1 as a rollback copy.

For a no-write checksum validation, omit the output ZIP argument.
The original ZIP includes Assets, Packages, ProjectSettings, UserSettings, results, venv, and root config files. Regenerable Unity Library/Logs/obj/.vs folders were deliberately omitted.

**Do not publish the unencrypted ZIP or the private decryption key.**
