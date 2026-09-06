import streamlit as st
import pandas as pd
import subprocess
import os
import tempfile
from pathlib import Path

st.set_page_config(page_title="EventWatch Risk Pipeline", layout="wide")

st.title("🛡️ EventWatch Impactful Classification Engine")
st.markdown("""
Upload your raw EventWatch feed export to automatically filter out noise, deduplicate stories, and evaluate the remaining events against the Resilinc EventWatch guidelines using our Multi-Role Council Debater Engine.
""")

uploaded_file = st.file_uploader("Upload Event File (Excel)", type=["xlsx"])

if uploaded_file is not None:
    st.success(f"File '{uploaded_file.name}' uploaded successfully!")
    
    if st.button("🚀 Run Classification Pipeline"):
        with st.spinner("Executing Pipeline... (This may take a while for large files)"):
            
            # Save uploaded file to a temporary location
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_input:
                tmp_input.write(uploaded_file.getvalue())
                tmp_input_path = tmp_input.name
                
            output_dir = os.path.join(os.getcwd(), "output")
            os.makedirs(output_dir, exist_ok=True)
            
            # Since the pipeline auto-generates the output name based on the input name,
            # we'll run the command and then find the newest file in the output directory.
            command = ["python", "-m", "pipeline.main", "--input", tmp_input_path]
            
            try:
                # Run the pipeline script
                process = subprocess.run(command, capture_output=True, text=True)
                
                if process.returncode == 0:
                    st.success("Pipeline executed successfully!")
                    
                    # Find the most recently created file in the output directory
                    output_files = list(Path(output_dir).glob("*.xlsx"))
                    if output_files:
                        latest_output = max(output_files, key=os.path.getctime)
                        
                        st.subheader("📊 Classification Results Preview")
                        
                        # Read the output Excel file
                        df_out = pd.read_excel(latest_output)
                        st.dataframe(df_out.head(100), use_container_width=True)
                        
                        st.markdown("### Download Full Report")
                        with open(latest_output, "rb") as f:
                            st.download_button(
                                label="📥 Download Processed Excel File",
                                data=f,
                                file_name=latest_output.name,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                    else:
                        st.error("Pipeline finished but no output file was found in the 'output' directory.")
                else:
                    st.error("An error occurred during pipeline execution.")
                    st.code(process.stderr)
                    
            except Exception as e:
                st.error(f"Execution failed: {str(e)}")
            finally:
                # Cleanup temporary input file
                if os.path.exists(tmp_input_path):
                    os.remove(tmp_input_path)

st.markdown("---")
st.markdown("### 📋 Output Format Description")
st.markdown("""
The final exported Excel file will contain the following strict 6-column structure:
1. **Feed Title**: The exact headline or title of the news event.
2. **Analyst Name**: The name of the analyst who originally processed the story (carried over from your input).
3. **Classification**: Binary classification indicating whether the event is **IMPACTFUL** or **NOT IMPACTFUL**.
4. **Event Type**: The specific assigned EventWatch category (e.g., *Merger / Acquisition*, *Factory Fire*, *Water Level / Drought*).
5. **Rationale**: A brief, logically sound explanation from the AI Debater Engine detailing exactly *why* the story was classified that way, explicitly citing the threshold guidelines (e.g., "Mapped partner involved", "Event is strictly past-tense with no ongoing disruption", etc.).
6. **Feedback**: An empty column provided for the Risk Management Process Owner or Analyst to manually leave feedback for future model iterations.
""")
