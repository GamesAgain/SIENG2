# Distributed & Nested demo

Select **Distributed & Nested Steganography** in the template list, then
click **Run Pipeline** and **Save Outputs**. All four steps have default inputs.
Open a step card to change them.

The three generated PNG images and RSA key pair are demo assets.
The private key is shared and unprotected; use your own key pair and password
for real data.

To recover the demo:

1. Use Extract Locomotive with both saved carrier images and
   `keys/recipient_private.pem` (no key password) to recover `image1.png`.
2. Extract LSB++ from the image2 carrier without encryption: `DemoPassword`.
3. Read the image3 carrier's Metadata Comment: `2026!`.
4. Join the fragments in that order and extract LSB++ from the recovered
   image1 using password `DemoPassword2026!`.
   The message is `This is a demo secret message.`

Both carriers are required to recover image1. Locomotive leaves pixels and
metadata readable, so fragments can also be read before recovering image1.
Splitting and joining the password is manual in this demo.

If you replace a cover with a different filename, select its new Previous
Output again in step 4. Keep the YAML and its asset folder together when moving
the template; paths in the YAML are relative to the YAML's directory.
