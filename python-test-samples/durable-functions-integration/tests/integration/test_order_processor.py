# Copyright (c) 2025 Amazon Web Services, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import boto3
import json
import os
import time
from decimal import Decimal
from aws_durable_execution_sdk_python_testing import DurableFunctionCloudTestRunner
from aws_durable_execution_sdk_python.execution import InvocationStatus

region = "us-east-1"

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb', region_name=region)


def test_cloud_order_processor_success():
    """Test the deployed order processor function in AWS"""

    # Create a cloud test runner pointing to the deployed function
    runner = DurableFunctionCloudTestRunner(
        function_name="order-processor-cloud-test:dev",
        region=region
    )

    # Invoke the function in AWS
    result = runner.run(
        input={"orderId": "cloud-integration-test-001"},
        timeout=30
    )

    # Verify execution succeeded
    assert result.status is InvocationStatus.SUCCEEDED

    # Parse and verify the result
    execution_result = result.result
    if isinstance(execution_result, str):
        execution_result = json.loads(execution_result)

    # Verify the workflow completed correctly
    assert execution_result["orderId"] == "cloud-integration-test-001"
    assert execution_result["status"] == "completed"
    assert len(execution_result["steps"]) == 3

    # Verify each step
    assert execution_result["steps"][0]["status"] == "validated"
    assert execution_result["steps"][1]["status"] == "paid"
    assert execution_result["steps"][1]["amount"] == 99.99
    assert execution_result["steps"][2]["status"] == "confirmed"
    
    # Verify persistence result
    assert "persistence" in execution_result
    assert execution_result["persistence"]["status"] == "persisted"
    assert execution_result["persistence"]["orderId"] == "cloud-integration-test-001"

    print("✅ Cloud integration test passed!")



def test_cloud_order_processor_with_invalid_input():
    """Test error handling in the cloud"""

    runner = DurableFunctionCloudTestRunner(
        function_name="order-processor-cloud-test:dev",
        region=region
    )

    # Test with missing orderId
    result = runner.run(
        input={},
        timeout=30
    )

    # Verify the execution failed as expected
    assert result.status is InvocationStatus.FAILED
    print("✅ Error handling test passed!")


def test_cloud_performance():
    """Measure real-world execution time"""
    runner = DurableFunctionCloudTestRunner(
        function_name="order-processor-cloud-test:dev",
        region=region
    )

    start_time = time.time()

    result = runner.run(
        input={"orderId": "performance-test"},
        timeout=30
    )

    execution_time = time.time() - start_time

    # Verify execution succeeded
    assert result.status is InvocationStatus.SUCCEEDED

    # Verify execution time is reasonable (should be ~10 seconds + overhead)
    assert execution_time >= 10, "Execution completed too quickly"
    assert execution_time <= 15, "Execution took too long"

    print(f"✅ Performance test passed! Execution time: {execution_time:.2f}s")


def test_dynamodb_persistence():
    """Test that orders are persisted to DynamoDB"""
    
    # Get the table name
    table_name = 'durable-functions-integration-Orders'
    table = dynamodb.Table(table_name)
    
    # Create unique order ID for this test
    order_id = f"dynamodb-test-{int(time.time())}"
    
    # Run the workflow
    runner = DurableFunctionCloudTestRunner(
        function_name="order-processor-cloud-test:dev",
        region=region
    )
    
    result = runner.run(
        input={"orderId": order_id},
        timeout=30
    )
    
    # Verify execution succeeded
    assert result.status is InvocationStatus.SUCCEEDED
    
    # Wait a moment for DynamoDB to be consistent
    time.sleep(2)
    
    # Query DynamoDB to verify the order was persisted
    try:
        response = table.get_item(Key={'orderId': order_id})
        
        # Verify item exists
        assert 'Item' in response, f"Order {order_id} not found in DynamoDB"
        
        item = response['Item']
        
        # Verify order data
        assert item['orderId'] == order_id
        assert item['status'] == 'completed'
        assert 'steps' in item
        assert 'completedAt' in item
        assert 'createdAt' in item
        assert 'ttl' in item
        
        # Verify amount was stored correctly
        assert 'amount' in item
        assert item['amount'] == Decimal('99.99')
        
        # Parse and verify steps
        steps = json.loads(item['steps'])
        assert len(steps) == 3
        assert steps[0]['status'] == 'validated'
        assert steps[1]['status'] == 'paid'
        assert steps[2]['status'] == 'confirmed'
        
        print(f"✅ DynamoDB persistence test passed! Order {order_id} found in table {table_name}")
        
    except Exception as e:
        print(f"❌ Failed to verify DynamoDB persistence: {e}")
        raise



