# Copyright (c) 2025 Amazon Web Services, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import os
import json
from datetime import datetime
from decimal import Decimal
import boto3
from aws_durable_execution_sdk_python import (
    DurableContext,
    durable_execution,
    durable_step,
)
from aws_durable_execution_sdk_python.config import Duration

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('ORDERS_TABLE_NAME', 'Orders')
table = dynamodb.Table(table_name)


@durable_step
def validate_order(step_context, order_id):
    """Validate the order data"""
    step_context.logger.info(f"Validating order {order_id}")
    return {"orderId": order_id, "status": "validated"}


@durable_step
def process_payment(step_context, order_id):
    """Process payment for the order"""
    step_context.logger.info(f"Processing payment for order {order_id}")
    return {"orderId": order_id, "status": "paid", "amount": 99.99}


@durable_step
def confirm_order(step_context, order_id):
    """Confirm the order"""
    step_context.logger.info(f"Confirming order {order_id}")
    return {"orderId": order_id, "status": "confirmed"}


@durable_step
def persist_order_to_dynamodb(step_context, order_data):
    """
    Persist the completed order to DynamoDB.
    
    This durable step ensures the order is saved exactly once,
    even if the function is interrupted and replayed.
    """
    order_id = order_data['orderId']
    step_context.logger.info(f"Persisting order {order_id} to DynamoDB")
    
    try:
        # Convert float to Decimal for DynamoDB
        item = {
            'orderId': order_id,
            'status': order_data['status'],
            'steps': json.dumps(order_data['steps']),  # Store steps as JSON string
            'completedAt': order_data.get('completedAt', datetime.utcnow().isoformat()),
            'createdAt': datetime.utcnow().isoformat(),
            'ttl': int(datetime.utcnow().timestamp()) + (30 * 24 * 60 * 60)  # 30 days TTL
        }
        
        # Add amount if present (convert to Decimal)
        for step in order_data.get('steps', []):
            if 'amount' in step:
                item['amount'] = Decimal(str(step['amount']))
                break
        
        # Put item in DynamoDB
        response = table.put_item(Item=item)
        
        step_context.logger.info(f"Successfully persisted order {order_id} to DynamoDB")
        
        return {
            "orderId": order_id,
            "status": "persisted",
            "tableName": table_name,
            "timestamp": item['createdAt']
        }
        
    except Exception as e:
        step_context.logger.error(f"Failed to persist order {order_id}: {str(e)}")
        raise

@durable_execution
def lambda_handler(event, context: DurableContext):
    """
    Main Lambda handler for the order processing durable workflow.
    
    Workflow steps:
    1. Validate order
    2. Process payment
    3. Wait 10 seconds (simulates external confirmation)
    4. Confirm order
    5. Persist order to DynamoDB
    """
    order_id = event['orderId']
    
    # Step 1: Validate order
    validation_result = context.step(validate_order(order_id))
    
    # Step 2: Process payment
    payment_result = context.step(process_payment(order_id))
    
    # Wait for 10 seconds to simulate external confirmation
    context.wait(Duration.from_seconds(10))
    
    # Step 3: Confirm order
    confirmation_result = context.step(confirm_order(order_id))
    
    # Build order data
    order_data = {
        "orderId": order_id,
        "status": "completed",
        "steps": [validation_result, payment_result, confirmation_result],
        "completedAt": datetime.utcnow().isoformat()
    }
    
    # Step 4: Persist order to DynamoDB
    persistence_result = context.step(persist_order_to_dynamodb(order_data))
    
    # Return final result including persistence confirmation
    return {
        "orderId": order_id,
        "status": "completed",
        "steps": [validation_result, payment_result, confirmation_result],
        "persistence": persistence_result,
        "completedAt": order_data["completedAt"]
    }
