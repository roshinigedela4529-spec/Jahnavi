"""Cuts Kaveri out of each photo (transparent PNG) using rembg's person-segmentation model."""
import sys, glob, os
from rembg import remove, new_session
from PIL import Image
model = sys.argv[1] if len(sys.argv) > 1 else 'birefnet-portrait'
sess = new_session(model)
for p in sorted(glob.glob('photos/*.jpg')):
    out = remove(Image.open(p), session=sess, alpha_matting=False, post_process_mask=True)
    out.save('cutouts/' + os.path.basename(p).replace('.jpg', '.png'))
    print('done', p)
