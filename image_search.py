#%%
from DeepImageSearch import Load_Data, Search_Setup

# Load images from a folder
image_list = Load_Data().from_folder(["/home/hattajr/lab/ikmimart/.trash/images"])

 # Set up the search engine, You can load 'vit_base_patch16_224_in21k', 'resnet50' etc more then 500+ models 
st = Search_Setup(image_list=image_list, model_name='efficientnetv2_rw_s.ra2_in1k', pretrained=True, image_count=None)

# Index the images
st.run_index()

# Get metadata
metadata = st.get_image_metadata_file()

# Add new images to the index
# st.add_images_to_index(['image_path_1', 'image_path_2'])

# Get similar images
test_imgs = ["/home/hattajr/lab/ikmimart/.trash/test_images/0004-0001.png",
"/home/hattajr/lab/ikmimart/.trash/test_images/8998898851137.png",
"/home/hattajr/lab/ikmimart/.trash/test_images/8999988888866.png",
"/home/hattajr/lab/ikmimart/.trash/test_images/9311931024036.png",]

for img in test_imgs:
    print("ground truth: ", img)
    print(st.get_similar_images(image_path=img, number_of_images=2))

# Plot similar images
# st.plot_similar_images(image_path=test_imgs[0], number_of_images=9)

# Update metadata
# metadata = st.get_image_metadata_file()
# %%
test_imgs = [
# "/home/hattajr/lab/ikmimart/.trash/test_images/0004-0001.png",
# "/home/hattajr/lab/ikmimart/.trash/test_images/8998898851137.png",
# "/home/hattajr/lab/ikmimart/.trash/test_images/8999988888866.png",
# "/home/hattajr/lab/ikmimart/.trash/test_images/9311931024036.png",
"/home/hattajr/lab/ikmimart/.trash/test_images/belibis1.jpg",
"/home/hattajr/lab/ikmimart/.trash/test_images/belinis2.jpg",
]
for img in test_imgs:
    print("ground truth: ", img)
    st.plot_similar_images(image_path = img, number_of_images=2)
#%%
import timm


timm.list_models(pretrained=True)