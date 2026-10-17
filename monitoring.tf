resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_sns_topic" "remediation" {
  name = "${var.project_name}-remediation-trigger"
}

resource "aws_cloudwatch_metric_alarm" "unhealthy_hosts" {
  alarm_name          = "${var.project_name}-unhealthy-hosts"
  alarm_description   = "Triggers when ALB reports unhealthy targets"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = var.unhealthy_host_threshold
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    TargetGroup  = aws_lb_target_group.main.arn_suffix
    LoadBalancer = aws_lb.main.arn_suffix
  }

  alarm_actions = [aws_sns_topic.alerts.arn, aws_sns_topic.remediation.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

resource "aws_iam_role" "remediation" {
  name = "${var.project_name}-remediation-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_cloudwatch_log_group" "remediation" {
  name              = "/aws/lambda/${var.project_name}-remediation"
  retention_in_days = 7
}

resource "aws_iam_role_policy" "remediation" {
  name = "EcsRemediationPolicy"
  role = aws_iam_role.remediation.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "ecs:UpdateService"
        Resource = aws_ecs_service.main.id
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.remediation.arn}:*"
      }
    ]
  })
}

data "archive_file" "remediation" {
  type        = "zip"
  source_file = "${path.module}/lambda/remediation.py"
  output_path = "${path.module}/.terraform/remediation.zip"
}

resource "aws_lambda_function" "remediation" {
  function_name    = "${var.project_name}-remediation"
  role             = aws_iam_role.remediation.arn
  runtime          = "python3.12"
  handler          = "remediation.handler"
  timeout          = 30
  filename         = data.archive_file.remediation.output_path
  source_code_hash = data.archive_file.remediation.output_base64sha256

  environment {
    variables = {
      CLUSTER_NAME = aws_ecs_cluster.main.name
      SERVICE_NAME = aws_ecs_service.main.name
    }
  }

  depends_on = [
    aws_iam_role_policy.remediation,
    aws_cloudwatch_log_group.remediation,
  ]
}

resource "aws_lambda_permission" "from_sns" {
  statement_id  = "AllowExecutionFromSNS"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.remediation.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.remediation.arn
}

resource "aws_sns_topic_subscription" "remediation" {
  topic_arn = aws_sns_topic.remediation.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.remediation.arn

  depends_on = [aws_lambda_permission.from_sns]
}
