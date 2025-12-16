document.addEventListener('DOMContentLoaded', function() {
    
    // --- 1. SALE FORM VALIDATION AND CONFIRMATION LOGIC ---
    const saleForm = document.getElementById('saleForm');

    if (saleForm) {
        saleForm.addEventListener('submit', function(event) {
            // Get the selected product ID
            const productId = saleForm.querySelector('select[name="product_id"]').value;
            // Get the quantity value
            const quantityInput = document.getElementById('saleQuantity');
            const quantity = parseInt(quantityInput.value, 10);

            // --- Client-Side Validation ---

            // Check if a product was selected
            if (!productId) {
                alert('Please select a product for the sale.');
                event.preventDefault(); // Stop form submission
                return;
            }

            // Check if quantity is valid
            if (isNaN(quantity) || quantity <= 0) {
                alert('Please enter a valid quantity greater than zero.');
                event.preventDefault(); // Stop form submission
                return;
            }
            
            // --- Confirmation (User Experience) ---
            const productName = saleForm.querySelector(`option[value="${productId}"]`).textContent;

            if (!confirm(`Confirm sale: ${quantity} units of ${productName.split('(')[0].trim()}?`)) {
                event.preventDefault(); // Stop form submission if user clicks Cancel
            }
        });
    }
    
    
    // --- 2. WATCHLIST TOGGLE LOGIC (AJAX) ---
    // Finds all buttons with the class 'watchlist-btn'
    document.querySelectorAll('.watchlist-btn').forEach(button => {
        button.addEventListener('click', function() {
            const productId = this.getAttribute('data-product-id');
            const card = this.closest('.product-card');

            // Send POST request to the Flask API endpoint
            fetch(`/toggle_watchlist/${productId}`, {
                method: 'POST',
                // Headers are crucial for POST requests carrying JSON
                headers: {
                    'Content-Type': 'application/json'
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Update button text and card style based on the new status
                    if (data.new_status === 1) {
                        this.innerHTML = '⭐ Watched';
                        card.classList.add('watched'); // For CSS styling
                    } else {
                        this.innerHTML = '☆ Watchlist';
                        card.classList.remove('watched');
                    }
                } else {
                    alert(`Error: ${data.message}`);
                }
            })
            .catch(error => {
                console.error('Error toggling watchlist:', error);
                alert('Failed to update watchlist due to a network error.');
            });
        });
    });

    
    // --- 3. FLASHED MESSAGE TIMEOUT (UX Improvement) ---
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(message => {
        setTimeout(() => {
            message.style.opacity = '0';
            message.style.transition = 'opacity 0.5s ease-out';
            setTimeout(() => message.remove(), 500); // Remove element after transition
        }, 5000); // 5 seconds
    });
});