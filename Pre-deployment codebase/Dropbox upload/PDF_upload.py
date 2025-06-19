import json
import re
import dropbox
import pandas as pd
from io import BytesIO
import pdfkit
import time
import os
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Tuple, Any
import logging
from dataclasses import dataclass
import random
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
EXCEL_FILE = '/Users/adamkuzee/MIT Dropbox/adam/LLM survey/FULL SURVEY/Code and data/FULL SURVEY data/Task instances/Unformatted/{INSET FILE NAME}'
SAVE_DIRECTORY = '/Users/adamkuzee/MIT Dropbox/adam/LLM survey/FULL SURVEY/Code and data/FULL SURVEY data/Task instances/Formatted'
SHEET_NAME = 'Sheet1'
SAVE_INTERVAL = 50  # Save Excel file every 50 rows
MAX_CONCURRENT_UPLOADS = 20  # Increased for better parallelization
MAX_RETRIES = 3
RETRY_DELAY = 1

# Model name mapping (placeholder names for now)
MODEL_NAMES = {
    'model1': 'GPT_4o_2025',
    'model2': 'Claude_3_Opus',
    'model3': 'Gemini_Ultra',
    'model4': 'GPT_4_Turbo',
    'model5': 'Claude_3_Sonnet'
}

# Dropbox token
DROPBOX_TOKEN = "sl.u.AFja3BrThYEsy5KU-O0f49LMhTOpi_B96Xl1sAlyG408ZBc67yCVwlK-aVUs2snMSPhCeDpD1HFAhdUgRjZq-fRbTG1YOZ5Z3B10SQXzOTpHpiC-i2PltdNusf_YCkOtS7I0EFCx0FXYyDHiLF2WhyV-HKlF3K4Lxt05wCgjDkUx6IL2k1U5nKomUL6FiAk9Q6ycYx_bhWJMSARGUkN3w5sJ6yFMcSsCSKaD6ZvwfuhB0u6WhF-vTl9MQrqCtm-J-o2lEZx-S8UVFfJwUUZf5W9OsISsSGaZG8UJx2WDU5RJxuI5SDaebvXge12A3Yb5vt_vj1UtmcUawavXHMJ0iw0wU3qAuCPzWbq4zc11d3PZjWIX6rmUQVRhbLTFx7_17QCbpDmc0bBOFaL5Afs7CI_D-iLDHnfcfxAFMaiAoOyg-5E3Lk1EKa3Ru7oRYZg3BM4PkpSmi0Nia7r7w-Rc4NWBVrWja_NZAC8o7-6CV1FaHJsVSUR_IpgjMH-Cumwxt2PRivsNaZ8cAMFJ9HSS6F37O6won0khJ1IrwhugzW56nppMd3Dr9BGNbDNaqd0K2y8fFmiVLnizGDbNAww89GzOd1lZYVqwq9B_hInDny96u6KuZUAI6rYdJfcPGHedV16e8xF8a6vLjjb2CzajswUCje77i-H_EvB3AFL3dvPK5Hv2NCBrOBp1Imsl4A1mpJNxsoYkuT-8lgVPOzJaEFFL_8SlhpfxqWEr6F6RqcdvYJeS0QIay_ss-9c-TZvJnYq4Gj9Zqr7CQWDcKwxLq7sV8TZ5YlOP9t-Myri9xG1d-r_EeSX6PztyaMrGpMZXmFEknrEpUOkZZmtxLvVvCbbnCsgGZQPFMSqcIRHLbFyaPpRu8glinwMtnjM1uYqdVSMntuaaXut6a_LIwFeLEj9M9zwrdUQY59TvKPYSntLXFn84ra-pHLPRAZ_ZQWEcQchqTrFI-ZvCdWgXSvmzB_uzl7XpFC68bhuFuVwIxfwN4wiV2F8d-_SJS-PQIwCj8gISAxuBYH40QEThOI_NHzbmRLMIm6wCHuJcm2rQuYYwUb7yptflOrgiQ1KY4LXKwk4CsZqD4yIsNXL-ejPLf6aMnnBm1_acf4TcAVtDFCJCSxZBecBdqsAQkJf3dORXsyhrAwsxoEFqweV8B442heaGEYeTKWrfnPOJMOY0tHAgaoiOcYZ1vAYl3A5wZbrl5fknf3skAfKo3pcmYK54-OE8KKYpysVX6YrrupmgrZqpz__vwrKR514UtPsXrbVRbhrcrjiiUMRRR_ybgTCIAtBhuRZVaVlmjBHJtUN4whisPZFuxtTJnYVATR-3Q0g7RtBmjmv87a6NJDg0qXUiELZKEDqipepca2OmX3EMWZnBXkuQPDTB41Era3YnpGtseUQ"

@dataclass
class TaskData:
    """Data structure for a single task with pre-computed IDs"""
    original_index: int
    occupation_id: str
    task_id: str
    job: str
    task: str
    order_models: str
    columns_to_process: Dict[str, str]  # column_name -> content

class DropboxUploader:
    def __init__(self):
        self.dbx = dropbox.Dropbox(DROPBOX_TOKEN)
        self.session = None
        
    async def setup_session(self):
        """Setup aiohttp session with connection pooling"""
        connector = aiohttp.TCPConnector(
            limit=MAX_CONCURRENT_UPLOADS * 2,
            limit_per_host=MAX_CONCURRENT_UPLOADS,
            ttl_dns_cache=300,
            use_dns_cache=True,
        )
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=300)
        )
        
    async def close_session(self):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()

    def verify_connection(self):
        """Verify Dropbox connection"""
        try:
            account = self.dbx.users_get_current_account()
            logger.info(f"Successfully connected to Dropbox account: {account.name.display_name}")
            return True
        except Exception as e:
            logger.error(f"Error connecting to Dropbox: {str(e)}")
            return False

def custom_css():
    """CSS styling for PDFs"""
    return """
        body {
            font-family: 'Times New Roman', Times, serif;
            font-size: 15pt;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.4;
        }
        h1 { font-size: 20pt; font-weight: bold; margin: 0.8em 0 0.4em; }
        h2 { font-size: 16pt; font-weight: bold; margin: 0.6em 0 0.3em; }
        h3 { font-size: 14pt; font-weight: bold; margin: 0.5em 0 0.25em; }
        ul, ol { margin: 0.8em 0; padding-left: 1.5em; }
        ul ul, ol ol, ul ol, ol ul { margin: 0.4em 0; }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 0.8em 0;
            font-size: 11pt;
        }
        th, td {
            padding: 6px;
            border: 1px solid #ddd;
            text-align: left;
        }
        img { max-width: 100%; height: auto; }
        @media print {
            body { margin: 0; }
            img { max-height: 100vh; }
        }
    """

def make_pdf(content, css=None):
    """Convert HTML to PDF with consistent formatting"""
    if not content or pd.isna(content):
        return None
    
    # Clean content
    content = str(content).replace("```html", "").replace("```", "")
    content = content.replace('""', '"')
    content = content.replace('\\"', '"')
    content = content.replace("\\'", "'")
    
    # Handle images
    content = re.sub(
        r'<img[^>]*src="https?://[^"]*"[^>]*>',
        '<div style="border: 1px solid #ccc; padding: 20px; text-align: center; margin: 10px 0; background-color: #f9f9f9;">This response references a nonexistent visual element</div>',
        content
    )

    # Create full HTML document
    full_html = f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
         {css if css else ""}
        </style>
    </head>
    <body>
        {content}
    </body>
    </html>
    """
    
    try:
        options = {
            'enable-local-file-access': None,
            'quiet': False,
            'page-size': 'A4',
            'margin-top': '0.75in',
            'margin-right': '0.75in',
            'margin-bottom': '0.75in',
            'margin-left': '0.75in',
            'encoding': 'UTF-8',
        }
        
        pdf_data = pdfkit.from_string(full_html, False, options=options)
        buffer = BytesIO(pdf_data)
        buffer.seek(0)
        return buffer
    except Exception as e:
        logger.error(f"Error generating PDF: {e}")
        raise

async def upload_to_dropbox_async(filename: str, file_stream: BytesIO, dbx) -> str:
    """Upload PDF to Dropbox with retry logic"""
    for attempt in range(MAX_RETRIES):
        try:
            upload_path = f"/Benchmark Storage ALL PDFS REORDERED 2-19/{filename}"
            dbx.files_upload(
                file_stream.getvalue(), 
                upload_path, 
                mode=dropbox.files.WriteMode.overwrite
            )
            shared_link = dbx.sharing_create_shared_link(upload_path)
            return shared_link.url
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                logger.error(f"Failed to upload {filename} after {MAX_RETRIES} attempts: {str(e)}")
                raise
            else:
                wait_time = RETRY_DELAY * (2 ** attempt)
                logger.warning(f"Upload attempt {attempt + 1} failed for {filename}, retrying in {wait_time}s")
                await asyncio.sleep(wait_time)

def precompute_ids(df: pd.DataFrame) -> List[TaskData]:
    """Pre-compute all occupation and task IDs"""
    logger.info("Pre-computing occupation and task IDs...")
    
    # Get unique occupations (jobs) and assign IDs
    unique_jobs = df['Job'].unique()
    job_to_occupation_id = {job: f"occupation_{i+1:03d}" for i, job in enumerate(unique_jobs)}
    
    # Create task data with pre-computed IDs
    task_data_list = []
    job_task_counters = {}  # Track task numbers within each job
    job_task_row_counters = {}  # Track row numbers within each job/task pair
    
    for idx, row in df.iterrows():
        job = row['Job']
        task = row['Task']
        occupation_id = job_to_occupation_id[job]
        
        # Get or initialize task number for this job/task combination
        job_task_key = (job, task)
        if job_task_key not in job_task_counters:
            job_task_counters[job_task_key] = len([k for k in job_task_counters.keys() if k[0] == job]) + 1
            job_task_row_counters[job_task_key] = 0
        
        # Increment row counter for this job/task pair
        job_task_row_counters[job_task_key] += 1
        task_number = job_task_counters[job_task_key]
        row_number = job_task_row_counters[job_task_key]
        
        # Create task_id in format: task_XXX_YY_Z
        occupation_num = int(occupation_id.split('_')[1])
        task_id = f"task_{occupation_num:03d}_{task_number:02d}_{row_number}"
        
        # Prepare columns to process
        columns_to_process = {}
        for col in ['Question', 'model1', 'model2', 'model3', 'model4', 'model5']:
            if col in row and not pd.isna(row[col]):
                columns_to_process[col] = row[col]
        
        task_data = TaskData(
            original_index=idx,
            occupation_id=occupation_id,
            task_id=task_id,
            job=job,
            task=task,
            order_models=row.get('order_models', ''),
            columns_to_process=columns_to_process
        )
        task_data_list.append(task_data)
    
    logger.info(f"Pre-computed IDs for {len(task_data_list)} tasks")
    logger.info(f"Found {len(unique_jobs)} unique occupations")
    
    return task_data_list

async def process_single_column(task_data: TaskData, column_name: str, content: str, uploader: DropboxUploader) -> Tuple[int, str, str]:
    """Process a single column (convert to PDF and upload)"""
    try:
        # Generate PDF in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=4) as executor:
            pdf_buffer = await loop.run_in_executor(
                executor, 
                make_pdf, 
                content, 
                custom_css()
            )
        
        if pdf_buffer:
            # Create filename based on column type
            if column_name == 'Question':
                # For Question column: just task_id.pdf
                filename = f"{task_data.task_id}.pdf"
            elif column_name.startswith('model'):
                # For model columns: task_id_model=ModelName.pdf
                model_name = MODEL_NAMES.get(column_name, column_name)
                filename = f"{task_data.task_id}_model={model_name}.pdf"
            else:
                # Fallback for any other columns
                filename = f"{task_data.task_id}_{column_name}.pdf"
            
            url = await upload_to_dropbox_async(filename, pdf_buffer, uploader.dbx)
            return task_data.original_index, column_name, url
        else:
            return task_data.original_index, column_name, None
            
    except Exception as e:
        logger.error(f"Error processing {task_data.task_id}_{column_name}: {str(e)}")
        return task_data.original_index, column_name, None

async def process_task_batch(task_batch: List[TaskData], uploader: DropboxUploader, semaphore: asyncio.Semaphore) -> List[Tuple[int, Dict[str, Any]]]:
    """Process a batch of tasks with concurrency control"""
    async def process_task_with_semaphore(task_data: TaskData):
        async with semaphore:
            # Process all columns for this task
            tasks = []
            for column_name, content in task_data.columns_to_process.items():
                task_coro = process_single_column(task_data, column_name, content, uploader)
                tasks.append(task_coro)
            
            # Wait for all columns to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Build result dictionary
            task_result = {
                'occupation_id': task_data.occupation_id,
                'task_id': task_data.task_id,
                'Job': task_data.job,
                'Task': task_data.task,
                'order_models': task_data.order_models,
            }
            
            # Add column results
            for result in results:
                if isinstance(result, tuple) and len(result) == 3:
                    _, column_name, url = result
                    task_result[column_name] = url
                elif isinstance(result, Exception):
                    logger.error(f"Exception in column processing: {result}")
            
            return task_data.original_index, task_result
    
    # Process all tasks in the batch
    batch_tasks = [process_task_with_semaphore(task_data) for task_data in task_batch]
    batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
    
    # Filter out exceptions and return valid results
    valid_results = []
    for result in batch_results:
        if isinstance(result, tuple) and len(result) == 2:
            valid_results.append(result)
        elif isinstance(result, Exception):
            logger.error(f"Exception in task processing: {result}")
    
    return valid_results

def generate_latin_square_orders(n_models: int, n_rows: int) -> List[List[str]]:
    """
    Generate Latin Square randomized orders for models.
    Ensures each model appears in each position equally often.
    """
    model_names = list(MODEL_NAMES.values())  # ['GPT_4o_2025', 'Claude_3_Opus', etc.]
    
    if n_models != 5:
        raise ValueError("This implementation is designed for exactly 5 models")
    
    # Generate all possible Latin Square rows for 5 models
    # A 5x5 Latin Square where each model appears once in each row and column
    base_squares = [
        [0, 1, 2, 3, 4],
        [1, 2, 3, 4, 0],
        [2, 3, 4, 0, 1],
        [3, 4, 0, 1, 2],
        [4, 0, 1, 2, 3]
    ]
    
    # Convert to model names
    latin_square_orders = []
    for square_row in base_squares:
        order = [model_names[i] for i in square_row]
        latin_square_orders.append(order)
    
    # Shuffle the base square orders to add randomness while maintaining balance
    random.shuffle(latin_square_orders)
    
    # Repeat the pattern to cover all rows
    result_orders = []
    for i in range(n_rows):
        square_index = i % len(latin_square_orders)
        result_orders.append(latin_square_orders[square_index].copy())
    
    logger.info(f"Generated {n_rows} Latin Square randomized orders")
    logger.info(f"Each model will appear in each position approximately {n_rows/n_models:.1f} times")
    
    return result_orders

def apply_model_randomization(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Latin Square randomization to model columns and save order.
    """
    logger.info("Applying Latin Square randomization to model columns...")
    
    # Create a copy of the dataframe
    randomized_df = df.copy()
    
    # Get the model columns (should be URLs now)
    model_columns = ['model1', 'model2', 'model3', 'model4', 'model5']
    original_model_names = list(MODEL_NAMES.values())
    
    # Generate Latin Square orders
    n_rows = len(df)
    latin_orders = generate_latin_square_orders(5, n_rows)
    
    # Apply randomization to each row
    randomized_model_data = []
    order_strings = []
    
    for idx, (_, row) in enumerate(df.iterrows()):
        current_order = latin_orders[idx]
        
        # Create mapping from current model names to their URLs
        model_url_mapping = {}
        for i, model_col in enumerate(model_columns):
            original_model_name = original_model_names[i]
            model_url_mapping[original_model_name] = row[model_col]
        
        # Create new row with randomized order
        randomized_row_data = {}
        for i, model_name in enumerate(current_order):
            new_col = model_columns[i]  # model1, model2, etc.
            randomized_row_data[new_col] = model_url_mapping[model_name]
        
        randomized_model_data.append(randomized_row_data)
        
        # Create order string (concatenated list)
        order_string = ','.join(current_order)
        order_strings.append(order_string)
    
    # Update the dataframe with randomized model columns
    for i, model_col in enumerate(model_columns):
        randomized_df[model_col] = [row[model_col] for row in randomized_model_data]
    
    # Add the order_models column
    randomized_df['order_models'] = order_strings
    
    # Verify balance
    verify_latin_square_balance(order_strings, original_model_names)
    
    return randomized_df

def verify_latin_square_balance(order_strings: List[str], model_names: List[str]):
    """
    Verify that the Latin Square randomization is properly balanced.
    """
    logger.info("Verifying Latin Square balance...")
    
    # Count how many times each model appears in each position
    position_counts = {model: [0] * 5 for model in model_names}
    
    for order_string in order_strings:
        models_in_order = order_string.split(',')
        for position, model in enumerate(models_in_order):
            if model in position_counts:
                position_counts[model][position] += 1
    
    # Print balance verification
    logger.info("Model position distribution:")
    for model in model_names:
        counts = position_counts[model]
        logger.info(f"  {model}: {counts} (total: {sum(counts)})")
    
    # Check if reasonably balanced
    total_rows = len(order_strings)
    expected_per_position = total_rows / 5
    tolerance = 1  # Allow ±1 difference
    
    balanced = True
    for model in model_names:
        for pos_count in position_counts[model]:
            if abs(pos_count - expected_per_position) > tolerance:
                balanced = False
                break
    
    if balanced:
        logger.info("✓ Latin Square randomization is properly balanced")
    else:
        logger.warning("⚠ Latin Square randomization may not be perfectly balanced (acceptable for non-multiple-of-5 sample sizes)")

async def save_randomized_output(results_list: List[Dict[str, Any]]):
    """Save the final output with Latin Square randomized model order"""
    if not results_list:
        return
        
    try:
        # Convert to DataFrame
        results_df = pd.DataFrame(results_list)
        
        # Apply Latin Square randomization
        randomized_df = apply_model_randomization(results_df)
        
        # Reorder columns to put order_models near the beginning
        column_order = ['occupation_id', 'task_id', 'Job', 'Task', 'order_models',
                       'Question', 'model1', 'model2', 'model3', 'model4', 'model5']
        
        # Only include columns that exist in the DataFrame
        existing_columns = [col for col in column_order if col in randomized_df.columns]
        randomized_df = randomized_df[existing_columns]
        
        # Save randomized version
        randomized_output_file = os.path.join(SAVE_DIRECTORY, 'task_urls_HTML_benchmark_PDF_randomized_v3.xlsx')
        randomized_df.to_excel(randomized_output_file, index=False)
        
        logger.info(f"Saved randomized output: {len(randomized_df)} rows to {randomized_output_file}")
        
        # Also save a summary of the randomization
        summary_file = os.path.join(SAVE_DIRECTORY, 'randomization_summary.txt')
        with open(summary_file, 'w') as f:
            f.write("Latin Square Randomization Summary\n")
            f.write("=" * 40 + "\n\n")
            f.write(f"Total rows: {len(randomized_df)}\n")
            f.write(f"Models: {list(MODEL_NAMES.values())}\n\n")
            f.write("This randomization ensures each model appears in each position\n")
            f.write("(1st, 2nd, 3rd, 4th, 5th) approximately equally often.\n\n")
            f.write("The 'order_models' column contains the randomized order for each row.\n")
        
        return randomized_df
        
    except Exception as e:
        logger.error(f"Error saving randomized output: {str(e)}")
        return None

async def main():
    """Main processing function"""
    start_time = time.time()
    
    # Ensure output directory exists
    os.makedirs(SAVE_DIRECTORY, exist_ok=True)
    
    # Initialize uploader and verify connection
    uploader = DropboxUploader()
    if not uploader.verify_connection():
        logger.error("Failed to connect to Dropbox")
        return
    
    await uploader.setup_session()
    
    try:
        # Load Excel file
        logger.info(f"Loading Excel file: {EXCEL_FILE}")
        df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME, engine='openpyxl')
        logger.info(f"Loaded {len(df)} rows")
        
        # Pre-compute all IDs
        task_data_list = precompute_ids(df)
        
        # Initialize results array to maintain order
        total_tasks = len(task_data_list)
        results_array = [None] * total_tasks
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_UPLOADS)
        
        # Process in batches
        batch_size = 50  # Smaller batches for better memory management
        logger.info(f"Processing {total_tasks} tasks in batches of {batch_size}")
        
        processed_count = 0
        for start_idx in range(0, total_tasks, batch_size):
            end_idx = min(start_idx + batch_size, total_tasks)
            batch = task_data_list[start_idx:end_idx]
            
            batch_start_time = time.time()
            logger.info(f"Processing batch {start_idx//batch_size + 1}/{(total_tasks-1)//batch_size + 1}")
            
            # Process batch
            batch_results = await process_task_batch(batch, uploader, semaphore)
            
            # Store results in order
            for original_index, task_result in batch_results:
                results_array[original_index] = task_result
                processed_count += 1
            
            batch_duration = time.time() - batch_start_time
            logger.info(f"Batch completed in {batch_duration:.2f} seconds. Processed: {processed_count}/{total_tasks}")
            
            # Save progress periodically
            if processed_count % SAVE_INTERVAL == 0:
                await save_progress(results_array[:processed_count])
        
        # Final save with all results (original order)
        logger.info("Saving final results...")
        final_results = [r for r in results_array if r is not None]
        await save_progress(final_results)
        
        # Generate and save randomized version with Latin Square
        logger.info("Generating Latin Square randomized version...")
        randomized_df = await save_randomized_output(final_results)
        
        if randomized_df is not None:
            logger.info("✓ Successfully generated both original and randomized outputs")
        
    finally:
        await uploader.close_session()
    
    total_duration = time.time() - start_time
    logger.info(f"Processing completed in {total_duration:.2f} seconds")
    logger.info(f"Total tasks processed: {processed_count}")

async def save_progress(results_list: List[Dict[str, Any]]):
    """Save progress to Excel file"""
    if not results_list:
        return
        
    try:
        # Convert to DataFrame
        results_df = pd.DataFrame(results_list)
        
        # Reorder columns
        column_order = ['occupation_id', 'task_id', 'Job', 'Task', 'order_models', 
                       'Question', 'model1', 'model2', 'model3', 'model4', 'model5']
        
        # Only include columns that exist in the DataFrame
        existing_columns = [col for col in column_order if col in results_df.columns]
        results_df = results_df[existing_columns]
        
        # Save to Excel
        output_file = os.path.join(SAVE_DIRECTORY, 'task_urls_HTML_benchmark_PDF_optimized_v3.xlsx')
        results_df.to_excel(output_file, index=False)
        
        logger.info(f"Saved progress: {len(results_df)} rows to {output_file}")
        
    except Exception as e:
        logger.error(f"Error saving progress: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 