#!/usr/bin/env python3
import os
import aws_cdk as cdk
import json 

from aws_cdk import (
    Duration,
    Stack,
    aws_iam as iam,
    aws_lambda as lambda_,    
    aws_lambda_event_sources as event_sources,    
    aws_sqs as sqs_,
    aws_events as events,    
    aws_events_targets as targets,
    CfnOutput,
)
from aws_solutions_constructs.aws_sqs_lambda import SqsToLambda
from constructs import Construct

DIRNAME = os.path.dirname(__file__)


class LambdaEventBridgeSQSLambda(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        

        # Iam role to invoke lambda
        lambda_cfn_role = iam.Role(
            self,
            "CfnRole",
            assumed_by=iam.ServicePrincipal("events.amazonaws.com"),
        )
        lambda_cfn_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AWSLambdaExecute")
        )

        # lambda function for processing the incoming request from S3 bucket
        lambda_function = lambda_.Function(
            self,
            "EventGenerator",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="eventsGenerator.lambda_handler",
            code=lambda_.Code.from_asset(os.path.join(DIRNAME, "src")),
            timeout=Duration.minutes(1),
            memory_size=512,
            environment={
                "environment": "dev",                
            }            
        )

        lambda_function.add_function_url(auth_type = lambda_.FunctionUrlAuthType.NONE)
        
        
        # lambda version
        version = lambda_function.current_version

        # lambda policy
        lambda_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "events:CreateEventBus",
                    "events:PutEvents",                    
                ],
                resources=["*"],
            )
        )


        # SQS queue
        email_queue = sqs_.Queue(self, "EmailQueue")
        sftp_queue  = sqs_.Queue(self, "SftpQueue")
        tpapi_queue = sqs_.Queue(self, "TpapiQueue")
        

        # EventBridge Rule

        email_rule = self.create_rule(email_queue,'email')
        sftp_rule = self.create_rule(sftp_queue,'sftp')
        tpapi_rule= self.create_rule(tpapi_queue,'3papi') 
        


        email_integration = self.sqs_to_lambda_integration(email_queue,'Email',5)
        sftp_integration = self.sqs_to_lambda_integration(sftp_queue,'Sftp',2)
        tpapi_integration = self.sqs_to_lambda_integration(tpapi_queue,'Tpapi',3)

        # Outputs
        CfnOutput(
            self,
            "Lambda function",
            description="Lambda function",
            value=lambda_function.function_arn
        )

    def sqs_to_lambda_integration(self, queue, preference,input_rate):
       return SqsToLambda(self, preference+'OutboundProcessor',
            lambda_function_props=lambda_.FunctionProps(
                handler="eventProcessor.lambda_handler",
                code=lambda_.Code.from_asset(os.path.join(DIRNAME, "src")),                
                runtime=lambda_.Runtime.PYTHON_3_11,
                function_name=preference+'-processor',                           
            ),
            existing_queue_obj= queue,
            sqs_event_source_props=event_sources.SqsEventSourceProps(
                    batch_size=1,
                    max_concurrency = input_rate
            )                                    
        )

    def create_rule(self, queue, preference):
        eventPattern = {
                            "source": [{
                                        "equals-ignore-case": "content-generator"
                                       }],
                            "detail.preferenceDistribution": [{
                                   "equals-ignore-case": preference
                             }]
                       }               
                                                    
        target_queue = events.CfnRule.TargetProperty(arn= queue.queue_arn,id = preference+'-queue-target')        
        return events.CfnRule(self,preference+"-rule",event_pattern=eventPattern, targets=[target_queue])
    

app = cdk.App()
filestack = LambdaEventBridgeSQSLambda(app, "LambdaEventBridgeSQSLambda")

app.synth()
