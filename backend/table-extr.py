import camelot
import pandas as pd

def pdf_to_excel(pdf_file_path, excel_file_path, flavor='lattice'):
    # Extract tables using Camelot; try flavor 'lattice' for bordered tables or 'stream' for others
    tables = camelot.read_pdf(pdf_file_path, pages='all', flavor=flavor)
    
    # Create an Excel writer object using pandas
    with pd.ExcelWriter(excel_file_path, engine='openpyxl') as writer:
        # Loop through the extracted tables and write each to a separate Excel sheet
        for i, table in enumerate(tables):
            sheet_name = f'Table_{i+1}'
            # The DataFrame is stored in table.df
            table.df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"Written {sheet_name}")

if __name__ == "__main__":
    # Use a raw string or forward slashes for Windows paths if needed.
    pdf_file = r'C:\Users\Michael Webb\Desktop\Programming Projects\uwi-gpt\docs\fst_undergraduate_handbook_2023-2024.pdf'
    excel_file = 'excel_file.xlsx'
    
    # If your PDF tables have borders, 'lattice' is recommended; otherwise, try 'stream'
    pdf_to_excel(pdf_file, excel_file, flavor='lattice')
    print("Conversion complete!")
