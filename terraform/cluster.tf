# The ECS cluster that holds the DOCex services. Adopt the existing one.

resource "aws_ecs_cluster" "docex" {
  name = "docex-cluster"

  # The console-created cluster carries this block (logging = DEFAULT). We
  # declare it so the import changes NOTHING — config must match reality.
  configuration {
    execute_command_configuration {
      logging = "DEFAULT"
    }
  }
}

import {
  to = aws_ecs_cluster.docex
  id = "docex-cluster"
}
