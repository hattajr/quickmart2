
(() => {
  const startCameraBtn = document.getElementById('start-camera-btn');
  const cameraContainer = document.getElementById('camera-container');

  if (startCameraBtn) {
    startCameraBtn.addEventListener('click', () => {
      htmx.ajax('GET', '/show-camera', {
        target: '#camera-container',
        swap: 'innerHTML'
      });
    });
  }

  document.body.addEventListener('htmx:afterSwap', (event) => {
    if (event.detail.target.id === 'camera-container') {
      startCamera();
    }
  });
function startCamera() {
  const video = document.getElementById('video');
  if (!video) {
    console.error('Video element not found');
    return;
  }

  navigator.mediaDevices.getUserMedia({ video: true })
    .then(stream => {
      video.srcObject = stream;

      // Wait until video is ready before calling play
      video.onloadedmetadata = () => {
        video.play().catch(error => {
          console.error("Video play failed:", error);
        });
      };
    })
    .catch(error => {
      alert("Camera permission is required.");
      console.error("Camera error:", error);
    });
}

  window.takePhoto = function () {
    const video = document.getElementById('video');
    const canvas = document.getElementById('canvas');
    const fileInput = document.getElementById('file-input');
    const form = document.getElementById('upload-form');

    if (!video || video.videoWidth === 0 || video.videoHeight === 0) {
      alert("Camera is not ready. Please wait a moment.");
      return;
    }

    const context = canvas.getContext('2d');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    try {
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
    } catch (err) {
      console.error("Error drawing video to canvas:", err);
      alert("Failed to capture photo. Try again.");
      return;
    }

    canvas.toBlob(blob => {
      if (!blob) {
        console.error("Failed to create blob from canvas.");
        alert("Failed to process photo.");
        return;
      }

      const file = new File([blob], 'photo.jpg', { type: 'image/jpeg' });
      const dataTransfer = new DataTransfer();
      dataTransfer.items.add(file);
      fileInput.files = dataTransfer.files;

      form.requestSubmit();
    }, 'image/jpeg', 0.95);
  }
})();

//     const startCameraBtn = document.getElementById('start-camera-btn');
    // const cameraContainer = document.getElementById('camera-container');

    // // Load camera UI on button click via HTMX
    // startCameraBtn.addEventListener('click', () => {
      // htmx.ajax('GET', '/show-camera', {target: '#camera-container', swap: 'innerHTML'});
    // });

    // // Listen for HTMX content swapped event
    // document.body.addEventListener('htmx:afterSwap', (event) => {
      // if (event.detail.target.id === 'camera-container') {
        // startCamera();
      // }
    // });

    // // Start camera and show video element
    // function startCamera() {
      // const video = document.getElementById('video');
      // if (!video) {
        // console.error('Video element not found');
        // return;
      // }

      // navigator.mediaDevices.getUserMedia({ video: true })
        // .then(stream => {
          // video.srcObject = stream;
          // video.play();
        // })
        // .catch(error => {
          // alert("Camera permission is required.");
          // console.error("Camera error:", error);
        // });
    // }

    // // Take photo, convert to Blob, attach to file input, submit form
// function takePhoto() {
  // const video = document.getElementById('video');
  // const canvas = document.getElementById('canvas');
  // const fileInput = document.getElementById('file-input');
  // const form = document.getElementById('upload-form');

  // if (!video || video.videoWidth === 0 || video.videoHeight === 0) {
    // alert("Camera is not ready. Please wait a moment.");
    // return;
  // }

  // const context = canvas.getContext('2d');
  // canvas.width = video.videoWidth;
  // canvas.height = video.videoHeight;

  // try {
    // context.drawImage(video, 0, 0, canvas.width, canvas.height);
  // } catch (err) {
    // console.error("Error drawing video to canvas:", err);
    // alert("Failed to capture photo. Try again.");
    // return;
  // }

  // canvas.toBlob(blob => {
    // if (!blob) {
      // console.error("Failed to create blob from canvas.");
      // alert("Failed to process photo.");
      // return;
    // }

    // const file = new File([blob], 'photo.jpg', { type: 'image/jpeg' });
    // const dataTransfer = new DataTransfer();
    // dataTransfer.items.add(file);
    // fileInput.files = dataTransfer.files;

    // form.requestSubmit(); // HTMX will send it
  // }, 'image/jpeg', 0.95);  // High quality JPEG
// }






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

// const video = document.getElementById('video');
// const canvas = document.getElementById('canvas');
// const fileInput = document.getElementById('file-input');
// const form = document.getElementById('upload-form');

// function startCamera() {
    // navigator.mediaDevices.getUserMedia({ video: true })
        // .then(stream => {
            // video.srcObject = stream;
        // })
        // .catch(error => {
            // alert("Camera permission is required.");
            // console.error("Camera error:", error);
        // });
// }

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
