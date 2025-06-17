import streamlit as st
import pandas as pd
import zipfile

def load_data():
    # Load chargers and headroom CSV files
    chargers = pd.read_csv("chargers.csv")
    headroom = pd.read_csv("headroom.csv")

    # Open ZIP file and read CSV inside it
    with zipfile.ZipFile("cleaned_dft.zip") as z:
        # Print files inside ZIP to confirm (optional, can be removed)
        st.write("Files inside ZIP:", z.namelist())
        # Assume first file inside ZIP is the CSV we want
        with z.open(z.namelist()[0]) as f:
            cleaned_dft = pd.read_csv(f)

    # Optional processing
    cleaned_dft = cleaned_dft.sort_values("year").drop_duplicates(subset=["count_point_id"], keep="last")

    return chargers, cleaned_dft, headroom

def main():
    st.title("EV Charger Site Analyser")
    st.write("Upload your ranked sites CSV")

    uploaded_file = st.file_uploader("Upload your CSV", type=["csv"])

    if uploaded_file is not None:
        user_data = pd.read_csv(uploaded_file)
        st.write("Preview of your uploaded sites:")
        st.dataframe(user_data.head())

    try:
        chargers, cleaned_dft, headroom = load_data()
        st.write("Chargers data sample:")
        st.dataframe(chargers.head())

        st.write("Cleaned DFT data sample:")
        st.dataframe(cleaned_dft.head())

        st.write("Headroom data sample:")
        st.dataframe(headroom.head())

        # Your further app logic goes here...

    except Exception as e:
        st.error(f"Error loading data: {e}")

if __name__ == "__main__":
    main()
