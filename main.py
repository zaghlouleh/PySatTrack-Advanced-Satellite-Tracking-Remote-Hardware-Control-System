import logging
import sys
from ttkthemes import ThemedTk

# Modular Configurations & Views
import config
from views.main_view import MainView

def main():
    # Configure logging system
    logging.basicConfig(
        filename='script.log', 
        level=logging.DEBUG, 
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logging.info("Satellite Tracking application initiated.")
    
    try:
        # Initialize the interface with configured theme
        root = ThemedTk(theme=config.THEME_NAME)
        
        # Instantiate main visual views
        app = MainView(root)
        
        # Start event main loop execution
        root.mainloop()
        
    except Exception as e:
        logging.critical(f"Critical exception occurred inside main event runner: {str(e)}")
        print("Fatal System Error:", e)
        sys.exit(1)

if __name__ == "__main__":
    main()