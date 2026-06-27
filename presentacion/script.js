document.addEventListener('DOMContentLoaded', () => {
  const slides = document.querySelectorAll('.slide');
  const prevBtn = document.getElementById('prevBtn');
  const nextBtn = document.getElementById('nextBtn');
  const progressBar = document.getElementById('progressBar');
  const slideCounter = document.getElementById('slideCounter');
  
  let currentSlide = 0;
  const totalSlides = slides.length;

  function updateSlides() {
    slides.forEach((slide, index) => {
      if (index === currentSlide) {
        slide.classList.add('active');
        // Small reset animation on enter
        const content = slide.querySelector('.slide-content');
        if (content) {
          content.style.transform = 'translateY(10px)';
          setTimeout(() => content.style.transform = 'translateY(0)', 50);
        }
      } else {
        slide.classList.remove('active');
      }
    });

    // Update Progress Bar
    const progress = ((currentSlide) / (totalSlides - 1)) * 100;
    progressBar.style.width = `${progress}%`;

    // Update Counter
    slideCounter.textContent = `${currentSlide + 1} / ${totalSlides}`;

    // Update Buttons State
    prevBtn.style.opacity = currentSlide === 0 ? '0.5' : '1';
    prevBtn.style.cursor = currentSlide === 0 ? 'not-allowed' : 'pointer';
    
    nextBtn.style.opacity = currentSlide === totalSlides - 1 ? '0.5' : '1';
    nextBtn.style.cursor = currentSlide === totalSlides - 1 ? 'not-allowed' : 'pointer';
  }

  function nextSlide() {
    if (currentSlide < totalSlides - 1) {
      currentSlide++;
      updateSlides();
    }
  }

  function prevSlide() {
    if (currentSlide > 0) {
      currentSlide--;
      updateSlides();
    }
  }

  nextBtn.addEventListener('click', nextSlide);
  prevBtn.addEventListener('click', prevSlide);

  // Keyboard navigation
  document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight' || e.key === ' ') {
      nextSlide();
    } else if (e.key === 'ArrowLeft') {
      prevSlide();
    }
  });

  // Initial setup
  updateSlides();
});
