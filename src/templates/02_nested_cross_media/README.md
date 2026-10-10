# Nested Concealment & Cross-Media demo

Select **Nested Concealment & Cross-Media Key Distribution** from the template
list, then click **Run Pipeline** and **Save Outputs**. All four steps are ready.
You receive only `image1.png`, `image3.png`, and `song.mp3`.
The image2 carrier is concealed inside image1.

## Pipeline

1. Locomotive encrypts `files/document.pdf` using the demo public key and
   distributes it across image2 and image3.
2. Locomotive hides the step 1 image2 output inside image1, using password
   `NestedDemoPassword2026!`.
3. Metadata adds `NestedDemoPassword` to image1's Comment (iTXt), preserving
   the Locomotive bytes after IEND.
4. Metadata adds `2026!` to song.mp3's User Text tag (`TXXX`), with description
   `RecoveryPasswordPart2`.

## Recovery

1. Use Extract Metadata on the final image1 and song. Join image1's Comment
   first, then song's User Text `RecoveryPasswordPart2`:
   `NestedDemoPassword` + `2026!` = `NestedDemoPassword2026!`.
2. Use Extract Locomotive on image1 with that password. Save the recovered
   file as `image2.png`.
3. Use Extract Locomotive on recovered image2 and the final image3 together,
   with `keys/recipient_private.pem` (no key password). Save `document.pdf`.

The recovered PDF should be byte-for-byte identical to `files/document.pdf`.
Both image2 and image3 are required for the inner Locomotive payload.

## Demo assets and limits

The three PNGs, one-page PDF, short synthesized MP3 melody, and RSA 3072 key
pair were created for this demo. The private key is shared and unprotected.
The password and both fragments are also included openly in the YAML and
this README. Use your own credentials and inputs for real data.

Password splitting/joining is manual; metadata fragments are plain text.
The MP3 is needed to obtain part 2 when you do not already know the password.
The pipeline does not check that an MP3 is present when extracting image1
with a password you already have.

Open a step card to change defaults. If you change image2's or image1's
filename, reselect its Previous Output in step 2 or step 3 respectively.
Keep the YAML and its asset folder together when moving the template;
asset paths are relative to the YAML directory.
