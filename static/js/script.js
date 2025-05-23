// const video = document.getElementById('video');
// const canvas = document.getElementById('canvas');
// const fileInput = document.getElementById('file-input');
// const form = document.getElementById('upload-form');

// // Ask for camera permission and stream
// navigator.mediaDevices.getUserMedia({ video: true })
    // .then(stream => {
        // video.srcObject = stream;
    // })
    // .catch(error => {
        // alert("Camera permission is required.");
        // console.error("Camera error:", error);
    // });

// function takePhoto() {
    // const context = canvas.getContext('2d');
    // canvas.width = video.videoWidth;
    // canvas.height = video.videoHeight;

    // context.drawImage(video, 0, 0, canvas.width, canvas.height);
    // canvas.toBlob(blob => {
        // const file = new File([blob], 'photo.jpg', { type: 'image/jpeg' });
        // const dataTransfer = new DataTransfer();
        // dataTransfer.items.add(file);
        // fileInput.files = dataTransfer.files;

        // form.requestSubmit(); // Triggers HTMX form post
    // }, 'image/jpeg');
// }

const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const fileInput = document.getElementById('file-input');
const form = document.getElementById('upload-form');

function startCamera() {
    navigator.mediaDevices.getUserMedia({ video: true })
        .then(stream => {
            video.srcObject = stream;
        })
        .catch(error => {
            alert("Camera permission is required.");
            console.error("Camera error:", error);
        });
}

function takePhoto() {
    const context = canvas.getContext('2d');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(blob => {
        const file = new File([blob], 'photo.jpg', { type: 'image/jpeg' });
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        fileInput.files = dataTransfer.files;

        form.requestSubmit(); // Triggers HTMX form post
    }, 'image/jpeg');
}
